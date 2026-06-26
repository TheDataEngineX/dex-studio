"""Shared FastAPI dependencies used across all routers."""

from __future__ import annotations

import contextlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Annotated, Any

from dataenginex.engine import DexBackend
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dex_studio import _engine as _dex_engine
from dex_studio.auth import RequiresEngine, RequiresLogin, has_password, is_authenticated
from dex_studio.config import load_projects
from dex_studio.nav import (
    NAV_GROUPS,
    active_group_id,
    breadcrumbs,
    build_two_rail,
    cmd_palette_pages,
)

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


def _ns(label: str, href: str, icon: str) -> dict[str, str]:
    return {"label": label, "href": href, "icon": icon}


_NEXT_HOME = [
    _ns("Explore data sources", "/data/sources", "database"),
    _ns("Run a pipeline", "/data/pipelines", "workflow"),
    _ns("Open the AI playground", "/intelligence/playground", "sparkles"),
]

# Most-specific prefixes first; first match wins.
_NEXT_BY_PREFIX: list[tuple[str, list[dict[str, str]]]] = [
    (
        "/data/sources",
        [
            _ns("Build a pipeline", "/data/pipelines", "workflow"),
            _ns("Design the data flow", "/data/transforms", "git-fork"),
        ],
    ),
    (
        "/data/pipelines",
        [
            _ns("Design the data flow", "/data/transforms", "git-fork"),
            _ns("View lineage", "/data/lineage", "git-merge"),
            _ns("Query results in SQL", "/data/sql", "terminal"),
        ],
    ),
    (
        "/data/transforms",
        [
            _ns("Query in SQL", "/data/sql", "terminal"),
            _ns("View in warehouse", "/data/warehouse", "table-2"),
            _ns("Check data quality", "/data/quality", "shield-check"),
            _ns("View lineage", "/data/lineage", "git-merge"),
        ],
    ),
    (
        "/data/sql",
        [
            _ns("View in warehouse", "/data/warehouse", "table-2"),
            _ns("Browse the catalog", "/data/catalog", "book"),
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
        ],
    ),
    (
        "/data/warehouse",
        [
            _ns("Query in SQL", "/data/sql", "terminal"),
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
            _ns("Check data quality", "/data/quality", "shield-check"),
        ],
    ),
    (
        "/data/catalog",
        [
            _ns("Query in SQL", "/data/sql", "terminal"),
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
            _ns("Check data quality", "/data/quality", "shield-check"),
        ],
    ),
    (
        "/data/lakehouse",
        [
            _ns("Query in SQL", "/data/sql", "terminal"),
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
        ],
    ),
    (
        "/data/quality",
        [
            _ns("View pipelines", "/data/pipelines", "workflow"),
            _ns("Set up alerts", "/secops/alerts", "bell"),
        ],
    ),
    (
        "/data/lineage",
        [
            _ns("Design transforms", "/data/transforms", "git-fork"),
            _ns("Query in SQL", "/data/sql", "terminal"),
        ],
    ),
    (
        "/data",
        [
            _ns("Run a pipeline", "/data/pipelines", "workflow"),
            _ns("Query in SQL", "/data/sql", "terminal"),
        ],
    ),
    (
        "/intelligence/models",
        [
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
            _ns("Track experiments", "/intelligence/experiments", "flask-conical"),
            _ns("Check drift", "/intelligence/drift", "activity"),
        ],
    ),
    (
        "/intelligence/predictions",
        [
            _ns("Inspect the models", "/intelligence/models", "boxes"),
            _ns("Check drift", "/intelligence/drift", "activity"),
            _ns("Explore features", "/intelligence/features", "layers"),
        ],
    ),
    (
        "/intelligence/drift",
        [
            _ns("View models", "/intelligence/models", "boxes"),
            _ns("Set up alerts", "/secops/alerts", "bell"),
        ],
    ),
    (
        "/intelligence/playground",
        [
            _ns("Manage agents", "/intelligence/agents", "bot"),
            _ns("View traces", "/intelligence/traces", "activity"),
            _ns("Browse tools", "/intelligence/tools", "wrench"),
        ],
    ),
    (
        "/intelligence",
        [
            _ns("Open playground", "/intelligence/playground", "sparkles"),
            _ns("View models", "/intelligence/models", "boxes"),
            _ns("Make a prediction", "/intelligence/predictions", "zap"),
        ],
    ),
    (
        "/secops",
        [
            _ns("View audit log", "/secops/audit", "scroll-text"),
            _ns("Check alerts", "/secops/alerts", "bell"),
        ],
    ),
    (
        "/system",
        [
            _ns("View runs", "/system/runs", "history"),
            _ns("System metrics", "/system/metrics", "gauge"),
            _ns("Tail the logs", "/system/logs", "terminal"),
        ],
    ),
]


def next_steps(request: Request) -> list[dict[str, str]]:
    """Context-aware 'what can I do next' suggestions, keyed off the current page."""
    path = request.url.path
    if path in ("/", ""):
        return _NEXT_HOME
    for prefix, steps in _NEXT_BY_PREFIX:
        if path.startswith(prefix):
            return [s for s in steps if s["href"] != path]
    return []


def _has_project_config() -> bool:
    """Return True if a project config path is explicitly configured, even if engine failed."""
    if os.environ.get("DEX_CONFIG_PATH"):
        return True
    try:
        from dex_studio.config import load_prefs

        if load_prefs().default_config_path:
            return True
    except Exception:
        pass
    return False


def base_ctx(request: Request) -> dict[str, Any]:
    """Minimal template context available on every page.

    Heavy per-request engine stats (pipeline_count, agent_count, engine_latency_ms)
    are intentionally omitted. Routes that display them inject them explicitly.
    """
    eng = _dex_engine.get_engine()
    engine_offline = eng is None and _has_project_config()
    project_name = eng.config.project.name if eng else "No project"
    current_config = str(eng.config_path) if eng else ""
    projects = load_projects()
    health_status = "unknown"
    if eng is not None:
        cached = getattr(request.state, "_health_cache", None)
        if cached is None:
            with contextlib.suppress(Exception):
                cached = eng.health()
                request.state._health_cache = cached
        health_status = (cached or {}).get("status", "unknown")

    path = request.url.path
    _nav_rail, _nav_domain_label, _nav_domain_color, _nav_page_groups = build_two_rail(path)
    return {
        "request": request,
        "current_path": path,
        "project_name": project_name,
        "current_config": current_config,
        "engine_ready": eng is not None,
        "engine_offline": engine_offline,
        "health_status": health_status,
        "all_projects": [{"name": p.name, "config_path": str(p.config_path)} for p in projects],
        "css_v": _CSS_V,
        "csrf_token": _get_csrf_token(request),
        "flash": request.session.pop("flash", None),
        "next_steps": next_steps(request),
        # Navigation — single source of truth from nav.py
        "nav_groups": NAV_GROUPS,
        "nav_active_group": active_group_id(path),
        "nav_breadcrumbs": breadcrumbs(path),
        "nav_cmd_pages": cmd_palette_pages(),
        # Two-rail domain navigation
        "nav_rail": _nav_rail,
        "nav_domain_label": _nav_domain_label,
        "nav_domain_color": _nav_domain_color,
        "nav_page_groups": _nav_page_groups,
    }


def get_eng() -> DexBackend:
    """Return the engine or raise. Only for contexts where Depends isn't available (WebSocket)."""
    eng = _dex_engine.get_engine()
    if eng is None:  # pragma: no cover
        raise RuntimeError("Engine not initialized")
    return eng


# ---------------------------------------------------------------------------
# FastAPI Depends — preferred auth pattern for all new/migrated routes
# ---------------------------------------------------------------------------


def auth_dep(request: Request) -> None:
    """Dependency: raises RequiresLogin if no password or session is unauthenticated."""
    if not has_password():
        raise RequiresLogin()
    if not is_authenticated(request):
        raise RequiresLogin()


def engine_dep(_: Annotated[None, Depends(auth_dep)]) -> DexBackend:
    """Dependency: auth + loaded engine. Raises RequiresEngine if no project loaded."""
    eng = _dex_engine.get_engine()
    if eng is None:
        raise RequiresEngine()
    return eng


def engine_csrf_dep(
    request: Request,
    eng: Annotated[DexBackend, Depends(engine_dep)],
) -> DexBackend:
    """Dependency: auth + engine + CSRF. Use for all POST/mutation routes."""
    verify_csrf(request)
    return eng


# Convenient type aliases — use these in route signatures
ReadDep = Annotated[DexBackend, Depends(engine_dep)]
WriteDep = Annotated[DexBackend, Depends(engine_csrf_dep)]


# ---------------------------------------------------------------------------
# JSON/API deps — return HTTP 4xx instead of HTML redirects
# ---------------------------------------------------------------------------


def json_auth_dep(request: Request) -> None:
    """Auth for JSON routes — raises HTTP 401, not a session redirect."""
    if not has_password():
        raise HTTPException(status_code=401, detail="No password configured")
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


def json_engine_dep(_: Annotated[None, Depends(json_auth_dep)]) -> DexBackend:
    """Auth + loaded engine for JSON/SSE routes. Raises 503 when no project is loaded."""
    eng = _dex_engine.get_engine()
    if eng is None:
        raise HTTPException(status_code=503, detail="No project loaded")
    return eng


JsonReadDep = Annotated[DexBackend, Depends(json_engine_dep)]


def json_engine_csrf_dep(
    request: Request,
    eng: Annotated[DexBackend, Depends(json_engine_dep)],
) -> DexBackend:
    """Auth + engine + CSRF for JSON mutation routes (returns HTTP 403, not HTML redirect)."""
    expected = request.session.get("_csrf", "")
    if expected:
        provided = request.headers.get("X-CSRF-Token", "") or request.query_params.get("_csrf", "")
        if not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="CSRF validation failed.")
    return eng


JsonWriteDep = Annotated[DexBackend, Depends(json_engine_csrf_dep)]


# ---------------------------------------------------------------------------
# Shared helpers extracted to eliminate duplication across domain routers
# ---------------------------------------------------------------------------


def flash(request: Request, msg: str, kind: str = "success") -> None:
    """Write a flash message into the session for the next page render."""
    request.session["flash"] = {"msg": msg, "kind": kind}


def stub_page(request: Request, titles: dict[str, str]) -> HTMLResponse:
    """Render stub.html for not-yet-implemented pages.

    *titles* maps URL paths to human-readable page titles.
    """
    ctx = base_ctx(request) | {"page_title": titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
