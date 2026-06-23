"""Tests for dex_studio.auth — PBKDF2 password hashing, session auth, rate limiter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import (
    SESSION_COOKIE,
    _generate_password,
    _hash_password,
    _verify_password,
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
    def test_creates_hash_file_on_first_boot(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            setup_password()
        assert hash_file.exists()
        assert len(hash_file.read_text().strip()) > 0

    def test_noop_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "env-secret")
        hash_file = tmp_path / "auth.hash"
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            setup_password()
        assert not hash_file.exists()

    def test_noop_when_hash_file_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        hash_file = tmp_path / "auth.hash"
        original = _hash_password("existing-password")
        hash_file.write_text(original)
        with patch("dex_studio.auth._HASH_FILE", hash_file):
            setup_password()
        assert hash_file.read_text().strip() == original


class TestSessionCookieConstant:
    def test_value(self) -> None:
        assert SESSION_COOKIE == "dex_session"


class TestAuthRequired:
    def test_login_page_always_accessible(self) -> None:
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_onboarding_is_public(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "x" * 32)
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 200

    def test_protected_route_redirects_when_not_authed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "x" * 32)
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")
