"""Tests for dex_studio.auth — API-key gate, session token, auth_required."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from dex_studio.auth import SESSION_COOKIE, _expected_key, _make_token


class TestExpectedKey:
    def test_env_var_wins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "env-key")
        key_file = tmp_path / "api.key"
        key_file.write_text("file-key")
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = _expected_key()
        assert result == "env-key"

    def test_file_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        key_file = tmp_path / "api.key"
        key_file.write_text("file-key\n")
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = _expected_key()
        assert result == "file-key"

    def test_empty_env_falls_through(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "   ")
        key_file = tmp_path / "api.key"
        key_file.write_text("file-key")
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = _expected_key()
        assert result == "file-key"

    def test_no_key_returns_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        missing = tmp_path / "no.key"
        with patch("dex_studio.auth._KEY_FILE", missing):
            result = _expected_key()
        assert result is None


class TestMakeToken:
    def test_deterministic(self) -> None:
        assert _make_token("key") == _make_token("key")

    def test_different_keys_differ(self) -> None:
        assert _make_token("a") != _make_token("b")

    def test_sha256_hex_length(self) -> None:
        assert len(_make_token("x")) == 64

    def test_matches_expected_sha256(self) -> None:
        key = "test-key"
        expected = hashlib.sha256(f"dex-session:{key}".encode()).hexdigest()
        assert _make_token(key) == expected

    def test_token_differs_from_key(self) -> None:
        key = "my-key"
        assert _make_token(key) != key


class TestSessionCookieConstant:
    def test_value(self) -> None:
        assert SESSION_COOKIE == "dex_session"


class TestAuthRequired:
    def _app_with_auth_disabled(self) -> StarletteTestClient:
        import os

        os.environ.pop("DEX_STUDIO_API_KEY", None)
        from unittest.mock import patch

        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        return TestClient(app)

    def test_auth_disabled_no_redirect_to_login(self) -> None:
        client = self._app_with_auth_disabled()
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_auth_required_redirects_when_key_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "x" * 32)
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/onboarding", follow_redirects=False)
        # /onboarding is public — should NOT redirect to login
        assert resp.status_code == 200

    def test_protected_route_redirects_when_not_authed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "secret")
        monkeypatch.setenv("DEX_STUDIO_SESSION_SECRET", "x" * 32)
        with patch("dex_studio._engine.get_engine", return_value=None):
            from dex_studio.app import create_app

            app = create_app()
        client = TestClient(app)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("location", "")
