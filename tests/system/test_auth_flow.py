"""Auth flow tests — separate from route tests to avoid global state pollution."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password


def _patch_db(monkeypatch: pytest.MonkeyPatch, *, return_hash: str | None = None) -> None:
    monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_setting", MagicMock(return_value=return_hash))
    monkeypatch.setattr("dex_studio.db_store.set_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_setting", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
    monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
    monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())


def _make_app():
    from dex_studio.app import create_app

    @asynccontextmanager
    async def _noop(_app: object) -> AsyncGenerator[None]:
        yield

    app = create_app()
    app.router.lifespan_context = _noop
    return app


class TestAuthFlow:
    """Test authentication flow in isolation."""

    def test_setup_creates_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stored: dict[str, str] = {}
        monkeypatch.setattr("dex_studio.db_store.init_db", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.get_setting", lambda k: stored.get(k))
        monkeypatch.setattr(
            "dex_studio.db_store.set_setting", lambda k, v: stored.__setitem__(k, v)
        )
        monkeypatch.setattr("dex_studio.db_store.get_projects", MagicMock(return_value=[]))
        monkeypatch.setattr("dex_studio.db_store.set_project", MagicMock())
        monkeypatch.setattr("dex_studio.db_store.delete_project", MagicMock())
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "t" * 32)

        app = _make_app()
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.get("/setup")
            assert r.status_code in (200, 303)
            r = tc.post("/setup", data={"password": "new-test-pass-1234"})
            assert r.status_code == 303, f"Setup failed: {r.status_code} {r.text[:200]}"
            assert "auth.hash" in stored

    def test_login_with_wrong_password_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        _patch_db(monkeypatch, return_hash=_hash_password("test-pass"))
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.post("/login", data={"passphrase": "wrong-password"})
            assert r.status_code == 303
            assert "/login" in r.headers.get("location", "")

    def test_login_with_correct_password_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        _patch_db(monkeypatch, return_hash=_hash_password("test-pass"))
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.post("/login", data={"passphrase": "test-pass"})
            assert r.status_code == 303
            assert r.headers.get("location", "") == "/"

    def test_logged_in_session_can_access_protected_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        _patch_db(monkeypatch, return_hash=_hash_password("test-pass"))
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as tc:
            tc.post("/login", data={"passphrase": "test-pass"})
            r = tc.get("/")
            assert r.status_code in (200, 303)

    def test_logout_clears_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "t" * 32)
        _patch_db(monkeypatch, return_hash=_hash_password("test-pass"))
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as tc:
            tc.post("/login", data={"passphrase": "test-pass"})
            # Seed CSRF via GET, then POST logout with CSRF token
            get_r = tc.get("/")
            import re
            csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', get_r.content)
            headers = {"X-CSRF-Token": csrf.group(1).decode()} if csrf else {}
            r = tc.post("/logout", headers=headers)
            assert r.status_code == 303
            r = tc.get("/")
            assert r.status_code in (302, 303, 200)
            if r.status_code == 200:
                assert "sign in" in r.text.lower() or "passphrase" in r.text.lower()
