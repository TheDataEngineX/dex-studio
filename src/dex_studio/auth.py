"""DEX Studio auth — minimum viable API key gate.

Local mode: single API key stored in OS keychain (fallback: ~/.dex-studio/key).
Remote/hub mode: Bearer token from DEX API (passed as api_token in StudioConfig).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

import reflex as rx

__all__ = ["setup_auth", "login_page", "get_api_key", "SESSION_COOKIE"]

_log = logging.getLogger(__name__)
SESSION_COOKIE = "dex_session"
_KEY_FILE = Path.home() / ".dex-studio" / "api.key"
_ENV_KEY = "DEX_STUDIO_API_KEY"

_PUBLIC_ROUTES = {"/login", "/health", "/api/v1/health"}


def get_api_key() -> str:
    """Return the current API key — from env var, keychain, or generated key file."""
    env = os.environ.get(_ENV_KEY)
    if env:
        return env

    try:
        import keyring  # type: ignore[import-untyped]

        stored = keyring.get_password("dex-studio", "api_key")
        if stored:
            return str(stored)
    except Exception:
        pass

    if _KEY_FILE.exists():
        return _KEY_FILE.read_text().strip()

    key = secrets.token_urlsafe(32)
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key)
    _KEY_FILE.chmod(0o600)

    try:
        import keyring  # type: ignore[import-untyped]

        keyring.set_password("dex-studio", "api_key", key)
    except Exception:
        pass

    _log.warning("Generated new API key — stored at %s", _KEY_FILE)
    return key


def _make_session_token(api_key: str) -> str:
    """Derive a session token from the API key (not the key itself)."""
    return hashlib.sha256(f"dex-session:{api_key}".encode()).hexdigest()


class AuthState(rx.State):
    key_input: str = ""
    error: str = ""

    @rx.event
    def set_key_input(self, v: str) -> None:
        self.key_input = v

    @rx.event
    async def submit(self) -> None:
        entered = self.key_input.strip()
        if not entered:
            self.error = "API key required"
            return
        stored = get_api_key()
        if not secrets.compare_digest(entered, stored):
            self.error = "Invalid API key"
            return
        self.error = ""
        yield rx.redirect("/")


def login_page() -> rx.Component:
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("DEX Studio", size="5"),
                rx.text("Enter your API key to continue", size="2", color_scheme="gray"),
                rx.input(
                    placeholder="API key",
                    type="password",
                    value=AuthState.key_input,
                    on_change=AuthState.set_key_input,
                    width="100%",
                ),
                rx.cond(
                    AuthState.error != "",
                    rx.text(AuthState.error, color_scheme="red", size="2"),
                    rx.fragment(),
                ),
                rx.button(
                    "Sign in",
                    on_click=AuthState.submit,
                    width="100%",
                    color_scheme="indigo",
                ),
                rx.text(
                    "Tip: key in ~/.dex-studio/api.key or DEX_STUDIO_API_KEY",
                    size="1",
                    color_scheme="gray",
                ),
                spacing="4",
                width="320px",
                align="center",
            ),
            padding="8",
        ),
        height="100vh",
    )


def setup_auth(skip_auth: bool = False) -> None:
    """Reflex auth setup — no-op in dev; middleware wired in app.py for prod."""
    if skip_auth or os.environ.get("DEX_STUDIO_SKIP_AUTH", "").lower() in ("1", "true", "yes"):
        _log.info("Auth disabled (DEX_STUDIO_SKIP_AUTH or skip_auth=True)")
