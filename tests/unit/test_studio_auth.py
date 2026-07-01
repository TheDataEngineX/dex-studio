"""Tests for dex_studio.auth — PBKDF2 password hashing, session auth, rate limiter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
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

_SESSION_SECRET = "t" * 32


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
    def test_noop_when_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "some-passphrase")
        mock_set = MagicMock()
        monkeypatch.setattr("dex_studio.db_store.set_setting", mock_set)
        setup_password()
        mock_set.assert_not_called()

    def test_noop_when_db_hash_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        existing = _hash_password("existing-password")
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: existing)
        mock_set = MagicMock()
        monkeypatch.setattr("dex_studio.db_store.set_setting", mock_set)
        setup_password()
        mock_set.assert_not_called()

    def test_auto_generates_password_on_first_boot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: None)
        mock_set = MagicMock()
        monkeypatch.setattr("dex_studio.db_store.set_setting", mock_set)
        setup_password()
        mock_set.assert_called_once()
        key, stored_hash = mock_set.call_args[0]
        assert key == "auth.hash"
        assert len(stored_hash) > 32


class TestHasPassword:
    def test_true_when_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "some-passphrase")
        assert has_password()

    def test_true_when_db_hash_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: _hash_password("pw"))
        assert has_password()

    def test_false_when_no_env_var_and_no_db_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: None)
        assert not has_password()


class TestSetPassword:
    def test_writes_verifiable_hash(self) -> None:
        mock_set = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("dex_studio.db_store.set_setting", mock_set)
            set_password("MyP@ssw0rd!")
        mock_set.assert_called_once()
        key, stored_hash = mock_set.call_args[0]
        assert key == "auth.hash"
        assert _verify_password("MyP@ssw0rd!", stored_hash)

    def test_symbols_and_special_chars(self) -> None:
        pw = "P@$$w0rd!#%^&*()"
        mock_set = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("dex_studio.db_store.set_setting", mock_set)
            set_password(pw)
        _, stored_hash = mock_set.call_args[0]
        assert _verify_password(pw, stored_hash)

    def test_overwrites_existing_password(self) -> None:
        mock_set = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("dex_studio.db_store.set_setting", mock_set)
            set_password("old-password")
            set_password("new-password")
        assert mock_set.call_count == 2
        _, hash2 = mock_set.call_args_list[1][0]
        assert _verify_password("new-password", hash2)
        assert not _verify_password("old-password", hash2)


class TestSessionCookieConstant:
    def test_value(self) -> None:
        assert SESSION_COOKIE == "dex_session"


def _patch_db(monkeypatch: pytest.MonkeyPatch, *, return_hash: str | None = None) -> None:
    """Patch all db_store functions used during app lifecycle and request handling."""
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=return_hash))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())


class TestAuthRequired:
    def test_login_page_always_accessible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        assert TestClient(create_app()).get("/login").status_code == 200

    def test_setup_page_accessible_when_no_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=None)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        assert TestClient(create_app(), follow_redirects=False).get("/setup").status_code == 200

    def test_setup_page_redirects_to_login_when_password_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        resp = TestClient(create_app(), follow_redirects=False).get("/setup")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_setup_post_saves_password_and_redirects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        stored: dict[str, str] = {}
        monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: stored.get(k))
        monkeypatch.setattr(
            "dex_studio.db_store.set_setting", lambda k, v: stored.__setitem__(k, v)
        )
        monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        resp = TestClient(create_app(), follow_redirects=False).post(
            "/setup", data={"password": "MyStr0ng#Pass"}
        )
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")
        assert "auth.hash" in stored

    def test_setup_post_rejects_short_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=None)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        resp = TestClient(create_app()).post("/setup", data={"password": "short"})
        assert resp.status_code == 200

    def test_onboarding_is_public(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        assert (
            TestClient(create_app(), follow_redirects=False).get("/onboarding").status_code == 200
        )

    def test_protected_route_redirects_when_not_authed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_PASSPHRASE", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        resp = TestClient(create_app(), follow_redirects=False).get("/")
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")

    def test_protected_route_redirects_to_setup_when_no_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_PASSPHRASE", raising=False)
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", _SESSION_SECRET)
        _patch_db(monkeypatch, return_hash=None)
        monkeypatch.setattr("dex_studio._engine.get_engine", lambda: None)
        from dex_studio.app import create_app

        resp = TestClient(create_app(), follow_redirects=False).get("/")
        assert resp.status_code in (302, 303)
        assert "/setup" in resp.headers.get("location", "")
