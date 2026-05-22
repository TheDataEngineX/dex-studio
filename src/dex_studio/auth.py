"""DEX Studio auth — API-key gate using signed session cookies."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse

SESSION_COOKIE = "dex_session"
_KEY_FILE = Path.home() / ".dex-studio" / "api.key"


def _expected_key() -> str | None:
    """Return the configured API key, or None if auth is disabled."""
    env = os.environ.get("DEX_STUDIO_API_KEY", "").strip()
    if env:
        return env
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text().strip() or None
    return None


def _make_token(api_key: str) -> str:
    return hashlib.sha256(f"dex-session:{api_key}".encode()).hexdigest()


def auth_required(request: Request) -> RedirectResponse | None:
    """Return a redirect to /login if the session is invalid, else None.

    Usage in route handlers::

        if redir := auth_required(request):
            return redir
    """
    key = _expected_key()
    if not key:
        return None  # auth disabled
    token = request.session.get("token", "")
    if token == _make_token(key):
        return None
    return RedirectResponse(url="/login", status_code=303)


def validate_and_login(request: Request, submitted_key: str) -> bool:
    """Validate the submitted API key and set the session token if correct."""
    key = _expected_key()
    if not key or submitted_key.strip() == key:
        request.session["token"] = _make_token(key or "")
        return True
    return False


def logout(request: Request) -> None:
    request.session.clear()
