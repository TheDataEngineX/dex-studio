"""Shared FastAPI dependencies used across all routers."""

from __future__ import annotations

from typing import Any

from dataenginex.engine import DexBackend
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from dex_studio._engine import get_engine
from dex_studio.auth import auth_required


def templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates  # type: ignore[no-any-return]


def render(request: Request, template: str, ctx: dict[str, Any]) -> HTMLResponse:
    """Single call site for Jinja2Templates.TemplateResponse (new-API signature)."""
    tmpl: Jinja2Templates = request.app.state.templates  # type: ignore[no-any-return]
    return tmpl.TemplateResponse(request, template, ctx)  # type: ignore[arg-type]


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
    }


def require_auth(request: Request) -> RedirectResponse | None:
    return auth_required(request)


def require_engine(request: Request) -> RedirectResponse | None:
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
