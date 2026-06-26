"""Tests for dex_studio.auth — PBKDF2 password hashing, session auth, rate limiter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dex_studio.auth import (
    SESSION_COOKIE,
    _generate_password,
    _hash_password,
    _verify_password,
    has_password,
    set_password,
    setup_password,
)


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self) -> None:
        pw = "correct-horse-battery-staple"
        assert _verify_password(pw, _hash_password(pw))

    def test_wrong_password_fails(self) -> None:
        stored = _hash_password("correct")
        assert not _verify_password("wrong", stored)

    def test_two_hashes_of_same_password_differ(self) -> None:
        pw = "same-password"
        assert _hash_password(pw) != _hash_password(pw)

    def test_both_hashes_still_verify(self) -> None:
        pw = "same-password"
        h1, h2 = _hash_password(pw), _hash_password(pw)
        assert _verify_password(pw, h1)
        assert _verify_password(pw, h2)

    def test_empty_password_hashes_distinctly(self) -> None:
        stored = _hash_password("")
        assert _verify_password("", stored)
        assert not _verify_password("not-empty", stored)


class TestGeneratePassword:
    def test_format_three_groups(self) -> None:
        pw = _generate_password()
        assert pw.count("-") >= 2

    def test_minimum_length(self) -> None:
        assert len(_generate_password()) >= 20

    def test_unique_each_call(self) -> None:
        assert _generate_password() != _generate_password()


class TestSetupPassword:
    def test_noop_when_hash_file_exists(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        original = _hash_password("existing-password")
        hash_file.write_text(original)
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            setup_password()
        assert hash_file.read_text().strip() == original

    def test_password_auto_generated_on_first_boot(self, tmp_path: Path) -> None:
        """DEX auto-generates a password on first boot and writes the hash file."""
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            setup_password()
        assert hash_file.exists(), "hash file should be created on first boot"
        assert hash_file.stat().st_size > 0, "hash file should not be empty"


class TestHasPassword:
    def test_false_when_no_file(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            assert not has_password()

    def test_true_when_hash_file_exists(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text(_hash_password("some-password"))
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            assert has_password()

    def test_false_when_hash_file_empty(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        hash_file.write_text("   ")
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            assert not has_password()


class TestSetPassword:
    def test_writes_verifiable_hash(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            set_password("MyP@ssw0rd!")
            stored = hash_file.read_text().strip()
        assert _verify_password("MyP@ssw0rd!", stored)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "nested" / "dir" / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            set_password("any-password")
        assert hash_file.exists()

    def test_symbols_and_special_chars(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        pw = "P@$$w0rd!#%^&*()"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            set_password(pw)
            stored = hash_file.read_text().strip()
        assert _verify_password(pw, stored)

    def test_overwrites_existing_password(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            set_password("old-password")
            set_password("new-password")
            stored = hash_file.read_text().strip()
        assert _verify_password("new-password", stored)
        assert not _verify_password("old-password", stored)


class TestSessionCookieConstant:
    def test_value(self) -> None:
        assert SESSION_COOKIE == "dex_session"


def _set_test_hash(tmp_path: Path) -> Path:
    """Write a known password hash to a temp file and patch auth._HASH_FILE."""
    hf = tmp_path / "auth.hash"
    hf.write_text(_hash_password("secret"))
    return hf


class TestAuthRequired:
    def test_login_page_always_accessible(self) -> None:
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_setup_page_accessible_when_no_password(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.get("/setup")
        assert resp.status_code == 200

    def test_setup_page_redirects_to_login_when_password_exists(self, tmp_path: Path) -> None:
        hash_file = _set_test_hash(tmp_path)
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.get("/setup", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_setup_post_saves_password_and_redirects(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.post("/setup", data={"password": "MyStr0ng#Pass"}, follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")
        assert hash_file.exists()

    def test_setup_post_rejects_short_password(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.post("/setup", data={"password": "short"})
        assert resp.status_code == 200
        assert not hash_file.exists()

    def test_onboarding_is_public(self, tmp_path: Path) -> None:
        hash_file = _set_test_hash(tmp_path)
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 200

    def test_protected_route_redirects_when_not_authed(self, tmp_path: Path) -> None:
        hash_file = _set_test_hash(tmp_path)
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_protected_route_redirects_to_setup_when_no_password(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "auth.hash"
        with (
            patch("dex_studio.auth._HASH_FILE", hash_file),
            patch("dex_studio._engine.get_engine", return_value=None),
        ):
            from dex_studio.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/setup" in resp.headers.get("location", "")
