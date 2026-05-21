"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine
from dex_studio.utils import fmt_ts

router = APIRouter()


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def system_status(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    health = eng.health()
    components: list[dict[str, Any]] = []
    for name, val in health.get("components", {}).items():
        available = bool(val) if not isinstance(val, bool) else val
        components.append(
            {
                "name": name.replace("_", " ").title(),
                "available": available,
                "status": "ok" if available else "offline",
            }
        )
    ctx = base_ctx(request) | {
        "health": health,
        "components": components,
        "is_healthy": health.get("status") in ("ok", "healthy"),
    }
    return render(request, "system/status.html", ctx)


# ── Logs ──────────────────────────────────────────────────────────────────────


@router.get("/logs", response_class=HTMLResponse)
async def system_logs(request: Request, level: str = "INFO") -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    level_upper = level.upper()
    log_rows: list[dict[str, str]] = []
    _level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
    min_lvl = _level_order.get(level_upper, 1)
    try:
        events = eng.audit.get_events(limit=200) or []
        for e in events:
            evt_level = str(getattr(e, "status", "INFO")).upper()
            evt_lvl_n = _level_order.get(evt_level, 1)
            if evt_lvl_n < min_lvl:
                continue
            log_rows.append(
                {
                    "ts": fmt_ts(getattr(e, "timestamp", "")),
                    "level": evt_level,
                    "msg": f"[{getattr(e, 'action', '')}] {getattr(e, 'resource', '')}",
                }
            )
    except Exception:
        pass
    ctx = base_ctx(request) | {
        "logs": log_rows,
        "level": level_upper,
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
    }
    return render(request, "system/logs.html", ctx)


@router.get("/logs/stream")
async def logs_stream(request: Request, level: str = "INFO") -> EventSourceResponse:
    """SSE endpoint — streams new audit log entries as they arrive."""
    eng = get_eng()
    level_upper = level.upper()
    _level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
    min_lvl = _level_order.get(level_upper, 1)
    seen: set[str] = set()

    async def event_generator() -> Any:
        while True:
            if await request.is_disconnected():
                break
            try:
                events = eng.audit.get_events(limit=50) or []
                for e in reversed(events):
                    eid = str(getattr(e, "event_id", id(e)))
                    if eid in seen:
                        continue
                    seen.add(eid)
                    evt_level = str(getattr(e, "status", "INFO")).upper()
                    if _level_order.get(evt_level, 1) < min_lvl:
                        continue
                    ts = fmt_ts(getattr(e, "timestamp", ""))
                    col = _level_color(evt_level)
                    act = getattr(e, "action", "")
                    res = getattr(e, "resource", "")
                    row_html = (
                        f'<tr><td class="rt-TableCell">{ts}</td>'
                        f'<td class="rt-TableCell"><span class="rt-Badge"'
                        f' data-accent-color="{col}" data-variant="soft"'
                        f' data-size="1">{evt_level}</span></td>'
                        f'<td class="rt-TableCell">[{act}] {res}</td></tr>'
                    )
                    yield {"event": "log-entry", "data": row_html}
            except Exception:
                pass
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


def _level_color(level: str) -> str:
    return {"ERROR": "red", "WARNING": "orange", "DEBUG": "gray"}.get(level, "blue")


# ── Metrics ───────────────────────────────────────────────────────────────────


@router.get("/metrics", response_class=HTMLResponse)
async def system_metrics(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    stats = eng.pipeline_stats()
    models = eng.model_registry.list_models()
    lineage_count = len(eng.lineage.all_events) if eng.lineage else 0
    ctx = base_ctx(request) | {
        "pipeline_total": stats.get("total", 0),
        "pipeline_scheduled": stats.get("scheduled", 0),
        "pipeline_failed": stats.get("failed", 0),
        "model_count": len(models),
        "agent_count": len(eng.agents),
        "lineage_events": lineage_count,
    }
    return render(request, "system/metrics.html", ctx)


# ── Components ────────────────────────────────────────────────────────────────


@router.get("/components", response_class=HTMLResponse)
async def system_components(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    health = eng.health()
    components: list[dict[str, Any]] = []
    for name, val in health.get("components", {}).items():
        available = bool(val) if not isinstance(val, bool) else val
        components.append(
            {
                "name": name.replace("_", " ").title(),
                "available": available,
                "status": "ok" if available else "offline",
                "message": "" if available else "Not initialized",
            }
        )
    ctx = base_ctx(request) | {"components": components}
    return render(request, "system/components.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────


@router.get("/traces", response_class=HTMLResponse)
@router.get("/activity", response_class=HTMLResponse)
@router.get("/incidents", response_class=HTMLResponse)
@router.get("/settings", response_class=HTMLResponse)
@router.get("/connection", response_class=HTMLResponse)
async def system_stub(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    titles = {
        "/system/traces": "System Traces",
        "/system/activity": "Activity Log",
        "/system/incidents": "Incidents",
        "/system/settings": "Settings",
        "/system/connection": "Connection Pool",
    }
    ctx = base_ctx(request) | {"page_title": titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
