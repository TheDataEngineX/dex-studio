"""Root routes: /, /onboarding, /login, /logout."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio._engine import (
    USER_PROJECTS_DIR,
    copy_example_to_user_dir,
    find_starter_configs,
    find_user_projects,
    init_engine,
    validate_config_file,
)
from dex_studio.auth import logout, validate_and_login
from dex_studio.routers._deps import base_ctx, render, require_auth, require_engine

router = APIRouter()


# ── Project Hub (/") ─────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def hub(request: Request) -> HTMLResponse:
    if redir := require_auth(request):
        return redir  # type: ignore[return-value]
    if redir := require_engine(request):
        return redir  # type: ignore[return-value]
    from dex_studio.routers._deps import get_eng

    eng = get_eng()
    stats = eng.pipeline_stats()
    models = eng.model_registry.list_models()
    health = eng.health()
    agents_count = len(eng.agents)
    source_count = len(eng.config.data.sources or {})
    pipeline_count = stats.get("total", 0)

    ctx = base_ctx(request) | {
        "stats": stats,
        "pipeline_count": pipeline_count,
        "source_count": source_count,
        "model_count": len(models),
        "agent_count": agents_count,
        "health_status": health.get("status", "unknown"),
        "user_projects": [{"name": n, "path": str(p)} for n, p in find_user_projects()],
    }
    return render(request, "root/hub.html", ctx)


# ── Onboarding ──────────────────────────────────────────────────────────────


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request) -> HTMLResponse:
    user_projects = [{"name": n, "path": str(p), "source": "user"} for n, p in find_user_projects()]
    example_projects = [
        {"name": n, "path": str(p), "source": "example"} for n, p in find_starter_configs()
    ]
    ctx = {
        "request": request,
        "current_path": "/onboarding",
        "project_name": "DEX Studio",
        "engine_ready": False,
        "all_projects": user_projects + example_projects,
        "error": request.session.pop("onboarding_error", ""),
        "warnings": request.session.pop("onboarding_warnings", []),
        "default_projects_dir": str(USER_PROJECTS_DIR),
    }
    return render(request, "root/onboarding.html", ctx)


@router.post("/onboarding/open")
async def onboarding_open(
    request: Request,
    config_path: Annotated[str, Form()],
    is_example: Annotated[str, Form()] = "",
) -> RedirectResponse:
    path = config_path.strip()
    if not path:
        request.session["onboarding_error"] = "Enter or select a path to a dex.yaml file."
        return RedirectResponse("/onboarding", status_code=303)
    try:
        if is_example == "1":
            path = str(copy_example_to_user_dir(Path(path)))
        schema_errors, warnings = validate_config_file(path)
        if schema_errors:
            request.session["onboarding_error"] = schema_errors[0]
            return RedirectResponse("/onboarding", status_code=303)
        if warnings:
            request.session["onboarding_warnings"] = warnings
        init_engine(path)
    except Exception as exc:
        request.session["onboarding_error"] = str(exc)
        return RedirectResponse("/onboarding", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.post("/onboarding/create")
async def onboarding_create(
    request: Request,
    project_name: Annotated[str, Form()] = "",
    project_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    name = project_name.strip() or "my-project"
    slug = name.lower().replace(" ", "-")
    dest = (
        Path(project_path.strip()).expanduser().resolve()
        if project_path.strip()
        else (USER_PROJECTS_DIR / slug)
    )
    try:
        dest.mkdir(parents=True, exist_ok=True)
        config_file = dest / "dex.yaml"
        config_file.write_text(
            f"project:\n  name: {name}\n  version: 0.1.0\n\n"
            "data:\n  engine: duckdb\n  sources: {}\n  pipelines: {}\n\n"
            "ml:\n  tracker: builtin\n\n"
            "ai:\n  llm:\n    provider: ollama\n    model: llama3.2\n\n"
            "server:\n  host: 0.0.0.0\n  port: 17000\n"
        )
        schema_errors, warnings = validate_config_file(config_file)
        if schema_errors:
            request.session["onboarding_error"] = schema_errors[0]
            return RedirectResponse("/onboarding", status_code=303)
        if warnings:
            request.session["onboarding_warnings"] = warnings
        init_engine(config_file)
    except Exception as exc:
        request.session["onboarding_error"] = str(exc)
        return RedirectResponse("/onboarding", status_code=303)
    return RedirectResponse("/", status_code=303)


# ── Project switch ───────────────────────────────────────────────────────────


@router.post("/projects/switch")
async def switch_project(
    request: Request,
    config_path: Annotated[str, Form()],
) -> RedirectResponse:
    path = config_path.strip()
    if path:
        try:
            init_engine(path)
            _save_default(path)
        except Exception as exc:
            request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/", status_code=303)


@router.post("/projects/set-default")
async def set_default_project(
    request: Request,
    config_path: Annotated[str, Form()],
) -> RedirectResponse:
    path = config_path.strip()
    if path:
        try:
            init_engine(path)
            _save_default(path)
            request.session["flash"] = {"msg": "Default project saved", "kind": "success"}
        except Exception as exc:
            request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/", status_code=303)


def _save_default(config_path: str) -> None:
    from dex_studio.config import StudioPrefs, load_prefs, save_prefs

    p = load_prefs()
    save_prefs(
        StudioPrefs(
            theme=p.theme,
            window_width=p.window_width,
            window_height=p.window_height,
            host=p.host,
            port=p.port,
            native_mode=p.native_mode,
            default_config_path=config_path,
        )
    )


# ── Auth ─────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    ctx = {
        "request": request,
        "current_path": "/login",
        "project_name": "DEX Studio",
        "engine_ready": False,
        "error": request.session.pop("login_error", ""),
    }
    return render(request, "root/login.html", ctx)


@router.post("/login")
async def login_submit(
    request: Request,
    api_key: Annotated[str, Form()],
) -> RedirectResponse:
    if validate_and_login(request, api_key):
        return RedirectResponse("/", status_code=303)
    request.session["login_error"] = "Invalid API key."
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
async def logout_route(request: Request) -> RedirectResponse:
    logout(request)
    return RedirectResponse("/login", status_code=303)
