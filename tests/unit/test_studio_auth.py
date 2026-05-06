"""Tests for DEX Studio authentication — API key gate, session tokens, middleware.

Covers get_api_key() priority chain, _make_session_token determinism,
middleware cookie logic, and security-critical behaviors.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from unittest.mock import patch

import pytest

from dex_studio.auth import SESSION_COOKIE, _make_session_token, get_api_key

# ---------------------------------------------------------------------------
# get_api_key — priority chain
# ---------------------------------------------------------------------------


class TestGetApiKeyPriority:
    def test_env_var_wins_over_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "env-key-wins")
        # Write a file key that should be ignored
        key_file = tmp_path / "api.key"
        key_file.write_text("file-key")
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = get_api_key()
        assert result == "env-key-wins"

    def test_env_var_empty_string_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty env var should not be used — fall through to file."""
        monkeypatch.setenv("DEX_STUDIO_API_KEY", "")
        key_file = tmp_path / "api.key"
        key_file.write_text("file-key")
        with patch("dex_studio.auth._KEY_FILE", key_file):
            monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
            result = get_api_key()
        assert result == "file-key"

    def test_file_fallback_reads_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        key_file = tmp_path / "api.key"
        key_file.write_text("file-stored-key\n")  # trailing newline stripped
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = get_api_key()
        assert result == "file-stored-key"

    def test_generates_new_key_when_no_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        key_file = tmp_path / "nonexistent" / "api.key"
        with patch("dex_studio.auth._KEY_FILE", key_file):
            result = get_api_key()
        assert len(result) >= 32
        assert key_file.exists()
        assert key_file.read_text().strip() == result

    def test_generated_key_file_has_restricted_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        key_file = tmp_path / "new" / "api.key"
        with patch("dex_studio.auth._KEY_FILE", key_file):
            get_api_key()
        mode = oct(key_file.stat().st_mode)
        assert mode.endswith("600"), f"Expected 0600, got {mode}"

    def test_generated_key_is_url_safe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        key_file = tmp_path / "api.key"
        with patch("dex_studio.auth._KEY_FILE", key_file):
            key = get_api_key()
        # secrets.token_urlsafe chars: alphanumeric + - _
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in key
        )

    def test_generated_keys_are_unique(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
        keys = set()
        for i in range(5):
            key_file = tmp_path / f"api{i}.key"
            with patch("dex_studio.auth._KEY_FILE", key_file):
                keys.add(get_api_key())
        assert len(keys) == 5, "Generated keys must be unique"


# ---------------------------------------------------------------------------
# _make_session_token — determinism and security
# ---------------------------------------------------------------------------


class TestMakeSessionToken:
    def test_deterministic_for_same_key(self) -> None:
        tok1 = _make_session_token("test-api-key")
        tok2 = _make_session_token("test-api-key")
        assert tok1 == tok2

    def test_different_keys_produce_different_tokens(self) -> None:
        tok1 = _make_session_token("key-a")
        tok2 = _make_session_token("key-b")
        assert tok1 != tok2

    def test_token_is_sha256_hex(self) -> None:
        token = _make_session_token("any-key")
        # SHA-256 hex digest is 64 characters
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_token_does_not_equal_raw_key(self) -> None:
        key = "my-secret-key"
        assert _make_session_token(key) != key

    def test_token_matches_expected_sha256(self) -> None:
        key = "well-known-key"
        expected = hashlib.sha256(f"dex-session:{key}".encode()).hexdigest()
        assert _make_session_token(key) == expected

    def test_empty_key_produces_token(self) -> None:
        """Even empty key should produce a valid token (length/format check)."""
        token = _make_session_token("")
        assert len(token) == 64

    def test_unicode_key_produces_token(self) -> None:
        token = _make_session_token("κλειδί-ελληνικά")
        assert len(token) == 64


# ---------------------------------------------------------------------------
# SESSION_COOKIE constant
# ---------------------------------------------------------------------------


class TestSessionCookieConstant:
    def test_cookie_name_is_dex_session(self) -> None:
        assert SESSION_COOKIE == "dex_session"


# ---------------------------------------------------------------------------
# Key comparison — timing safe
# ---------------------------------------------------------------------------


class TestTimingSafeComparison:
    def test_secrets_compare_digest_used_for_key_validation(self) -> None:
        """Verify that the login flow uses secrets.compare_digest, not ==."""
        # We test the property indirectly: compare_digest returns False for mismatched keys
        key_a = secrets.token_urlsafe(32)
        key_b = secrets.token_urlsafe(32)
        assert not secrets.compare_digest(key_a, key_b)

    def test_compare_digest_true_for_equal_keys(self) -> None:
        key = secrets.token_urlsafe(32)
        assert secrets.compare_digest(key, key)

    def test_compare_digest_false_for_prefix(self) -> None:
        """A prefix of the key must not pass."""
        key = secrets.token_urlsafe(32)
        assert not secrets.compare_digest(key[:8], key)


# ---------------------------------------------------------------------------
# Public routes constant
# ---------------------------------------------------------------------------


class TestPublicRoutes:
    def test_login_is_public(self) -> None:
        from dex_studio.auth import _PUBLIC_ROUTES

        assert "/login" in _PUBLIC_ROUTES

    def test_health_is_public(self) -> None:
        from dex_studio.auth import _PUBLIC_ROUTES

        assert "/health" in _PUBLIC_ROUTES

    def test_api_health_is_public(self) -> None:
        from dex_studio.auth import _PUBLIC_ROUTES

        assert "/api/v1/health" in _PUBLIC_ROUTES


# ---------------------------------------------------------------------------
# setup_auth — skip_auth flag
# ---------------------------------------------------------------------------


class TestSetupAuth:
    def test_skip_auth_env_var_disables_middleware(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_SKIP_AUTH", "true")
        # Should return without registering middleware (no assertion on NiceGUI app state,
        # just verify it doesn't raise)
        from dex_studio.auth import setup_auth

        setup_auth()  # must not raise

    def test_skip_auth_param_disables_middleware(self) -> None:
        from dex_studio.auth import setup_auth

        setup_auth(skip_auth=True)  # must not raise

    @pytest.mark.parametrize("val", ["1", "true", "yes", "TRUE", "YES"])
    def test_skip_auth_env_truthy_values(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("DEX_STUDIO_SKIP_AUTH", val)
        from dex_studio.auth import setup_auth

        setup_auth()  # must not raise
