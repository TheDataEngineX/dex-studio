"""Shared FastAPI dependencies used across all routers."""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path
from typing import Any

from dataenginex.engine import DexBackend
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from dex_studio._engine import get_engine
from dex_studio.auth import auth_required

# ---------------------------------------------------------------------------
# Type alias used by _guard helpers in domain routers
# ---------------------------------------------------------------------------
type GuardResult = RedirectResponse | None

_STATIC_DIR = Path(__file__).parent.parent / "static"


def _css_version() -> str:
    """Return hex mtime of studio.css for cache-busting."""
    try:
        return format(int(os.path.getmtime(_STATIC_DIR / "studio.css")), "x")
    except OSError:
        return "0"


# Computed once at import time — changes only on server restart (i.e. new deploy).
_CSS_V: str = _css_version()


def templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates  # type: ignore[no-any-return]


def render(request: Request, template: str, ctx: dict[str, Any]) -> HTMLResponse:
    """Single call site for Jinja2Templates.TemplateResponse (new-API signature)."""
    tmpl: Jinja2Templates = request.app.state.templates  # type: ignore[no-any-return]
    return tmpl.TemplateResponse(request, template, ctx)  # type: ignore[arg-type]


def _get_csrf_token(request: Request) -> str:
    """Return existing CSRF token from session, generating one if absent."""
    token: str = request.session.get("_csrf", "")
    if not token:
        token = secrets.token_hex(24)
        request.session["_csrf"] = token
    return token


def verify_csrf(request: Request) -> None:
    """Raise 403 if no valid CSRF token is found.

    Accepts the token from two sources (checked in order):
    1. ``X-CSRF-Token`` request header — set by HTMX via ``hx-headers`` on body.
    2. ``_csrf`` query parameter — appended by base.html JS for native form POSTs
       (browsers cannot set custom headers on plain form submissions).

    Login / onboarding routes are exempt — they run before a session exists.
    """
    expected = request.session.get("_csrf", "")
    if not expected:
        return
    provided = request.headers.get("X-CSRF-Token", "") or request.query_params.get("_csrf", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def base_ctx(request: Request) -> dict[str, Any]:
    """Template context variables available on every page."""
    from dex_studio.config import load_projects

    eng = get_engine()
    project_name = eng.config.project.name if eng else "No project"
    current_config = str(eng.config_path) if eng else ""
    projects = load_projects()
    return {
        "request": request,
        "current_path": request.url.path,
        "project_name": project_name,
        "current_config": current_config,
        "engine_ready": eng is not None,
        "all_projects": [{"name": p.name, "config_path": str(p.config_path)} for p in projects],
        "css_v": _CSS_V,
        "csrf_token": _get_csrf_token(request),
    }


def require_auth(request: Request) -> RedirectResponse | None:
    return auth_required(request)


def require_engine() -> RedirectResponse | None:
    """Redirect to /onboarding when no project is loaded."""
    if get_engine() is None:
        return RedirectResponse(url="/onboarding", status_code=303)
    return None


def get_eng() -> DexBackend:
    """Return the engine or raise — use inside routes that already called require_engine."""
    eng = get_engine()
    if eng is None:  # pragma: no cover
        raise RuntimeError("Engine not initialized")
    return eng


# ---------------------------------------------------------------------------
# Shared helpers extracted to eliminate duplication across domain routers
# ---------------------------------------------------------------------------


def flash(request: Request, msg: str, kind: str = "success") -> None:
    """Write a flash message into the session for the next page render."""
    request.session["flash"] = {"msg": msg, "kind": kind}


def guard(request: Request) -> GuardResult:
    """Auth + engine check + CSRF for POST routes (used by data / ml / ai routers)."""
    if redir := require_auth(request) or require_engine():
        return redir
    if request.method == "POST":
        verify_csrf(request)
    return None


def stub_page(request: Request, titles: dict[str, str]) -> HTMLResponse:
    """Render stub.html for not-yet-implemented pages.

    *titles* maps URL paths to human-readable page titles.
    """
    ctx = base_ctx(request) | {"page_title": titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
