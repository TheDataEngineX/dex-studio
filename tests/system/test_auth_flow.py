"""Auth flow tests — separate from route tests to avoid global state pollution."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dex_studio.auth import _hash_password


@pytest.fixture(scope="module")
def auth_env(tmp_path_factory: pytest.TempPathFactory) -> Generator[tuple[Path, str]]:
    import dex_studio.auth as _auth_mod

    hash_file = tmp_path_factory.mktemp("auth_test") / "auth.hash"
    hash_file.write_text(_hash_password("test-pass"))
    orig = _auth_mod._HASH_FILE
    _auth_mod._HASH_FILE = hash_file

    os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)

    yield (hash_file, "test-pass")

    _auth_mod._HASH_FILE = orig


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

    def test_setup_creates_password(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        import dex_studio.auth as _auth_mod

        orig = _auth_mod._HASH_FILE
        hash_dir = tmp_path_factory.mktemp("auth_setup")
        hash_file = hash_dir / "auth.hash"
        # Remove any existing
        _auth_mod._HASH_FILE = hash_file

        with TestClient(_make_app(), raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.get("/setup")
            assert r.status_code in (200, 303)
            r = tc.post("/setup", data={"password": "new-test-pass-1234"})
            assert r.status_code == 303, f"Setup failed: {r.status_code} {r.text[:200]}"
            assert hash_file.exists()

        _auth_mod._HASH_FILE = orig

    def test_login_with_wrong_password_fails(self, auth_env) -> None:
        with TestClient(_make_app(), raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.post("/login", data={"passphrase": "wrong-password"})
            assert r.status_code == 303
            assert "/login" in r.headers.get("location", "")

    def test_login_with_correct_password_succeeds(self, auth_env) -> None:
        (_, password) = auth_env
        with TestClient(_make_app(), raise_server_exceptions=False, follow_redirects=False) as tc:
            r = tc.post("/login", data={"passphrase": password})
            assert r.status_code == 303
            assert r.headers.get("location", "") == "/"

    def test_logged_in_session_can_access_protected_page(self, auth_env) -> None:
        (_, password) = auth_env
        with TestClient(_make_app(), raise_server_exceptions=False, follow_redirects=False) as tc:
            tc.post("/login", data={"passphrase": password})
            r = tc.get("/")
            assert r.status_code in (200, 303)

    def test_logout_clears_session(self, auth_env) -> None:
        (_, password) = auth_env
        with TestClient(_make_app(), raise_server_exceptions=False, follow_redirects=False) as tc:
            tc.post("/login", data={"passphrase": password})
            r = tc.get("/logout")
            assert r.status_code == 303
            r = tc.get("/")
            assert r.status_code in (302, 303, 200)
            if r.status_code == 200:
                assert "sign in" in r.text.lower() or "passphrase" in r.text.lower()
