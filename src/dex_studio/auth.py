"""DEX Studio auth — API-key gate using signed session cookies."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse

SESSION_COOKIE = "dex_session"
_KEY_FILE = Path.home() / ".dex-studio" / "api.key"


def _generate_and_save_key() -> str:
    """Generate a new API key, persist it, and print it to stdout once."""
    key = secrets.token_urlsafe(32)
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key)
    print(  # noqa: T201 — intentional: must be visible on first boot
        "\n"
        "┌─────────────────────────────────────────────────────────┐\n"
        "│  DEX Studio — API key generated (shown once)            │\n"
        f"│  Key: {key:<51} │\n"
        "│  Saved to: ~/.dex-studio/api.key                        │\n"
        "│  Set DEX_STUDIO_API_KEY env var to override.            │\n"
        "└─────────────────────────────────────────────────────────┘\n",
        flush=True,
    )
    return key


def _expected_key() -> str:
    """Return the configured API key, auto-generating one on first run.

    Auth is always enabled — there is no auth-disabled mode.
    Override via DEX_STUDIO_API_KEY env var (e.g. for Docker / CI).
    """
    env = os.environ.get("DEX_STUDIO_API_KEY", "").strip()
    if env:
        return env
    if _KEY_FILE.exists():
        key = _KEY_FILE.read_text().strip()
        if key:
            return key
    return _generate_and_save_key()


def _make_token(api_key: str) -> str:
    return hashlib.sha256(f"dex-session:{api_key}".encode()).hexdigest()


def auth_required(request: Request) -> RedirectResponse | None:
    """Return a redirect to /login if the session is invalid, else None.

    Usage in route handlers::

        if redir := auth_required(request):
            return redir
    """
    key = _expected_key()
    token = request.session.get("token", "")
    if hmac.compare_digest(token, _make_token(key)):
        return None
    return RedirectResponse(url="/login", status_code=303)


def validate_and_login(request: Request, submitted_key: str) -> bool:
    """Validate the submitted API key and set the session token if correct."""
    key = _expected_key()
    if submitted_key.strip() == key:
        request.session["token"] = _make_token(key)
        return True
    return False


def logout(request: Request) -> None:
    request.session.clear()
