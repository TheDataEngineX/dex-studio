"""Root routes: /, /onboarding, /login, /logout."""

from __future__ import annotations

import contextlib
import datetime as _dt_mod
from pathlib import Path
from typing import Annotated, Any

import structlog
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
from dex_studio.auth import (
    MIN_PASSWORD_LEN,
    clear_rate_limit,
    get_client_ip,
    has_password,
    is_authenticated,
    logout,
    rate_limit_blocked,
    record_failed_login,
    reset_password,
    set_password,
    validate_and_login,
)
from dex_studio.routers._deps import ReadDep, WriteDep, _get_csrf_token, base_ctx, render
from dex_studio.utils import fmt_run_row

router = APIRouter()
log = structlog.get_logger().bind(src="router.root")


def _hub_layer_stats(eng: Any) -> tuple[list[dict[str, Any]], int]:
    """Return (layer_stats, extra_table_count) from the lakehouse, best-effort."""
    layer_stats: list[dict[str, Any]] = []
    table_count = 0
    _DESCS = {
        "bronze": "raw ingest — sources, files, streams",
        "silver": "cleaned, joined, masked",
        "gold": "modeled features, dashboards",
    }
    for layer in ("bronze", "silver", "gold"):
        with contextlib.suppress(Exception):
            tables = eng.warehouse_tables(layer) or []
            layer_stats.append(
                {
                    "layer": layer,
                    "count": len(tables),
                    "rows": "—",
                    "size": "—",
                    "desc": _DESCS[layer],
                }
            )
            table_count += len(tables)
    return layer_stats, table_count


def _hub_heatmap(eng: Any) -> list[int]:
    """Bucket pipeline run timestamps into 126 daily cells (18 weeks × 7 days)."""
    import datetime as _dt

    cells: list[int] = [0] * 126
    with contextlib.suppress(Exception):
        now = _dt.datetime.now(_dt.UTC)
        origin = now - _dt.timedelta(days=125)
        for r in eng.store.get_pipeline_runs()[-1000:]:
            ts = r.timestamp
            if not ts:
                continue
            if isinstance(ts, str):
                ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=_dt.UTC)
            delta = (ts - origin).days
            if 0 <= delta < 126:
                cells[delta] += 1
    return cells


def _hub_recent_runs(eng: Any) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for r in reversed(eng.store.get_pipeline_runs()[-7:]):
            runs.append(fmt_run_row(r))
    return runs


def _sparkbar_slot_col(slot_runs: list[Any]) -> dict[str, Any]:
    """Convert a list of runs in one sparkbar slot to a display column dict."""
    if not slot_runs:
        return {"status": "empty", "height": 10}
    statuses = [getattr(r, "status", "unknown") for r in slot_runs]
    has_running = any(s in ("running", "active") for s in statuses)
    has_fail = any(s in ("failed", "error") for s in statuses)
    status = "running" if has_running else ("fail" if has_fail else "ok")
    return {"status": status, "height": min(100, 20 + len(slot_runs) * 15)}


def _hub_sparkbar(eng: Any) -> list[dict[str, Any]]:  # noqa: C901
    """7-column sparkbar of today's pipeline runs (newest-last)."""
    import datetime as _dt

    cols: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        today_start = _dt.datetime.now(_dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_runs = []
        for r in eng.store.get_pipeline_runs()[-100:]:
            ts = r.timestamp
            if not ts:
                continue
            if isinstance(ts, str):
                ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=_dt.UTC)
            if ts >= today_start:
                today_runs.append(r)

        # Bucket into 7 slots (spread evenly across today's runs)
        slot_size = max(1, len(today_runs) // 7) if today_runs else 1
        slots: list[list[Any]] = [[] for _ in range(7)]
        for i, r in enumerate(today_runs[:49]):
            slots[min(i // slot_size, 6)].append(r)
        cols = [_sparkbar_slot_col(s) for s in slots]

    if not cols:
        cols = [{"status": "empty", "height": 10}] * 7
    return cols[:7]


def _run_verb(status: str) -> str:
    """Map a run status to a past-tense verb for display."""
    if status in ("success", "ok"):
        return "completed"
    if status in ("failed", "error"):
        return "failed"
    return "started"


def _hub_activity_feed(eng: Any) -> list[dict[str, Any]]:  # noqa: C901
    """Build cross-domain activity feed, max 12 rows, newest first."""
    import datetime as _dt

    rows: list[dict[str, Any]] = []
    now = _dt.datetime.now(_dt.UTC)

    def _ago(ts: Any) -> str:
        if not ts:
            return "—"
        if isinstance(ts, str):
            ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if not ts.tzinfo:
            ts = ts.replace(tzinfo=_dt.UTC)
        delta = now - ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs}h ago"
        return f"{hrs // 24}d ago"

    with contextlib.suppress(Exception):
        for r in reversed(eng.store.get_pipeline_runs()[-12:]):
            status = getattr(r, "status", "unknown")
            name = getattr(r, "pipeline_name", getattr(r, "pipeline", "pipeline"))
            rows.append(
                {
                    "domain": "data",
                    "icon": "workflow",
                    "desc": f"Pipeline {name} {_run_verb(status)}",
                    "sub": f"status: {status}",
                    "href": f"/data/pipelines/{name}",
                    "time_ago": _ago(getattr(r, "timestamp", None)),
                    "badge": "DATA",
                }
            )

    # Add placeholder system events if engine healthy
    with contextlib.suppress(Exception):
        health = eng.health()
        if health.get("status") in ("ok", "healthy"):
            rows.append(
                {
                    "domain": "system",
                    "icon": "heart-pulse",
                    "desc": "All system components healthy",
                    "sub": "engine · scheduler · db",
                    "href": "/system/status",
                    "time_ago": "now",
                    "badge": "OPS",
                }
            )

    rows = rows[:12]
    return rows


# ── Privacy alias — canonical home is /secops ─────────────────────────────────


@router.get("/privacy")
@router.get("/privacy/")
def privacy_redirect() -> RedirectResponse:
    """Redirect /privacy* → /secops (Governance nav maps here)."""
    return RedirectResponse(url="/secops", status_code=301)


# ── Project Hub ("/") ────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
def hub(request: Request, eng: ReadDep) -> HTMLResponse:
    log.debug("hub viewed", project=getattr(eng.config, "project", {}) and eng.config.project.name)
    stats = eng.pipeline_stats()
    health = eng.health()
    request.state._health_cache = health  # reuse in base_ctx, avoid second call
    source_count = len(eng.config.data.sources or {})
    layer_stats, extra_tables = _hub_layer_stats(eng)
    components = [
        {"name": k.replace("_", " ").title(), "ok": bool(v) if not isinstance(v, bool) else v}
        for k, v in health.get("components", {}).items()
    ]
    ctx = base_ctx(request) | {
        "stats": stats,
        "pipeline_count": stats.get("total", 0),
        "source_count": source_count,
        "model_count": len(eng.model_registry.list_models()),
        "agent_count": len(eng.agents),
        "table_count": source_count + extra_tables,
        "health_status": health.get("status", "unknown"),
        "layer_stats": layer_stats,
        "components": components,
        "recent_runs": _hub_recent_runs(eng),
        "heatmap_cells": _hub_heatmap(eng),
        "sparkbar_data": _hub_sparkbar(eng),
        "activity_feed": _hub_activity_feed(eng),
        "now_hour": _dt_mod.datetime.now().hour,
        "user_projects": [{"name": n, "path": str(p)} for n, p in find_user_projects()],
    }
    return render(request, "root/hub.html", ctx)


# ── Onboarding ──────────────────────────────────────────────────────────────


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request) -> HTMLResponse:
    log.debug("onboarding page viewed")
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
def onboarding_open(
    request: Request,
    config_path: Annotated[str, Form()],
    is_example: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    path = config_path.strip()
    if not path:
        request.session["onboarding_error"] = "Enter or select a path to a dex.yaml file."
        return RedirectResponse("/onboarding", status_code=303)
    try:
        if is_example == "1":
            path = str(copy_example_to_user_dir(Path(path)))
            log.info("example project copied", dest=path)
        schema_errors, warnings = validate_config_file(path)
        if schema_errors:
            log.warning("project config invalid", path=path, error=schema_errors[0])
            request.session["onboarding_error"] = schema_errors[0]
            return RedirectResponse("/onboarding", status_code=303)
        if warnings:
            log.warning("project config warnings", path=path, count=len(warnings))
            request.session["onboarding_warnings"] = warnings
        init_engine(path)
        log.info("project opened", path=path)
    except Exception as exc:
        log.error("project open failed", path=path, error=str(exc))
        request.session["onboarding_error"] = str(exc)
        return RedirectResponse("/onboarding", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.post("/onboarding/create")
def onboarding_create(
    request: Request,
    project_name: Annotated[str, Form()] = "",
    project_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    name = project_name.strip() or "my-project"
    slug = name.lower().replace(" ", "-")
    dest = (
        Path(project_path.strip()).expanduser().resolve()
        if project_path.strip()
        else (USER_PROJECTS_DIR / slug)
    )
    log.info("creating new project", name=name, dest=str(dest))
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
            log.error("new project config invalid", name=name, error=schema_errors[0])
            request.session["onboarding_error"] = schema_errors[0]
            return RedirectResponse("/onboarding", status_code=303)
        if warnings:
            log.warning("new project config warnings", name=name, count=len(warnings))
            request.session["onboarding_warnings"] = warnings
        init_engine(config_file)
        log.info("project created and opened", name=name, path=str(config_file))
    except Exception as exc:
        log.error("project creation failed", name=name, dest=str(dest), error=str(exc))
        request.session["onboarding_error"] = str(exc)
        return RedirectResponse("/onboarding", status_code=303)
    return RedirectResponse("/", status_code=303)


# ── Project switch ───────────────────────────────────────────────────────────


@router.post("/projects/switch")
def switch_project(
    request: Request,
    _: WriteDep,
    config_path: Annotated[str, Form()],
) -> RedirectResponse:
    path = config_path.strip()
    if path:
        try:
            init_engine(path)
            _save_default(path)
            log.info("project switched", path=path)
        except Exception as exc:
            log.error("project switch failed", path=path, error=str(exc))
            request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/", status_code=303)


@router.post("/projects/set-default")
def set_default_project(
    request: Request,
    _: WriteDep,
    config_path: Annotated[str, Form()],
) -> RedirectResponse:
    path = config_path.strip()
    if path:
        try:
            init_engine(path)
            _save_default(path)
            log.info("default project saved", path=path)
            request.session["flash"] = {"msg": "Default project saved", "kind": "success"}
        except Exception as exc:
            log.error("set default project failed", path=path, error=str(exc))
            request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/", status_code=303)


def _save_default(config_path: str) -> None:
    import dataclasses

    from dex_studio.config import load_prefs, save_prefs

    save_prefs(dataclasses.replace(load_prefs(), default_config_path=config_path))


# ── First-boot setup ─────────────────────────────────────────────────────────


@router.get("/setup", response_class=HTMLResponse, response_model=None)
def setup_page(request: Request, reset: bool = False) -> HTMLResponse | RedirectResponse:
    if not reset and has_password():
        return RedirectResponse(url="/login", status_code=303)
    if reset:
        reset_password()
        request.session["setup_error"] = ""
        log.info("password reset — hash file removed")
    ctx = {
        "request": request,
        "current_path": "/setup",
        "project_name": "DEX Studio",
        "engine_ready": False,
        "error": request.session.pop("setup_error", ""),
        "min_len": MIN_PASSWORD_LEN,
    }
    return render(request, "root/setup.html", ctx)


@router.post("/setup", response_model=None)
def setup_submit(
    request: Request,
    password: Annotated[str, Form()],
) -> RedirectResponse | HTMLResponse:
    if has_password():
        return RedirectResponse(url="/login", status_code=303)
    pw = password.strip()
    if len(pw) < MIN_PASSWORD_LEN:
        ctx = {
            "request": request,
            "current_path": "/setup",
            "project_name": "DEX Studio",
            "engine_ready": False,
            "error": f"Password must be at least {MIN_PASSWORD_LEN} characters.",
            "min_len": MIN_PASSWORD_LEN,
        }
        return render(request, "root/setup.html", ctx)
    set_password(pw)
    log.info("password set via setup page")
    return RedirectResponse(url="/login", status_code=303)


# ── Auth ─────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    if not has_password():
        return RedirectResponse(url="/setup", status_code=303)
    log.debug("login page viewed")
    ctx = {
        "request": request,
        "current_path": "/login",
        "project_name": "DEX Studio",
        "engine_ready": False,
        "error": request.session.pop("login_error", ""),
        "can_reset": True,
    }
    return render(request, "root/login.html", ctx)


@router.post("/login")
def login_submit(
    request: Request,
    passphrase: Annotated[str, Form()],
) -> RedirectResponse:
    ip = get_client_ip(request)
    if rate_limit_blocked(ip):
        log.warning("login blocked — rate limit", ip=ip)
        request.session["login_error"] = "Too many failed attempts. Try again in 5 minutes."
        return RedirectResponse("/login", status_code=303)
    if validate_and_login(request, passphrase):
        _get_csrf_token(request)
        clear_rate_limit(ip)
        log.info("login successful", ip=ip)
        return RedirectResponse("/", status_code=303)
    record_failed_login(ip)
    log.warning("login failed", ip=ip)
    request.session["login_error"] = "Invalid passphrase."
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
def logout_route(request: Request) -> RedirectResponse:
    log.info("user logged out", ip=request.client.host if request.client else "unknown")
    logout(request)
    return RedirectResponse("/login", status_code=303)
