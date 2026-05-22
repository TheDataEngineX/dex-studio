"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio.logstore import log_store
from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine

router = APIRouter()


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/status", response_class=HTMLResponse)
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
    level_upper = level.upper()
    records = log_store.recent(limit=200, min_level=level_upper)
    log_rows = [{"ts": r.ts, "level": r.level, "msg": r.msg} for r in records]
    ctx = base_ctx(request) | {
        "logs": log_rows,
        "level": level_upper,
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
    }
    return render(request, "system/logs.html", ctx)


@router.get("/logs/stream")
async def logs_stream(request: Request, level: str = "INFO") -> EventSourceResponse:
    """SSE endpoint — streams new structlog entries as they arrive (2s poll)."""
    level_upper = level.upper()
    last_seq = log_store.seq

    async def event_generator() -> Any:
        nonlocal last_seq
        while True:
            if await request.is_disconnected():
                break
            current_seq = log_store.seq
            if current_seq > last_seq:
                new_count = current_seq - last_seq
                records = log_store.recent(limit=new_count * 2, min_level=level_upper)
                for r in reversed(records[:new_count]):
                    lc = r.level.lower()
                    mono = "font-family:'Fira Code',monospace"
                    row_html = (
                        f"<tr>"
                        f'<td class="rt-TableCell"'
                        f' style="font-size:11px;white-space:nowrap;{mono}">'
                        f"{r.ts}</td>"
                        f'<td class="rt-TableCell">'
                        f'<span class="dex-log-badge dex-log-{lc}">'
                        f"{r.level}</span></td>"
                        f'<td class="rt-TableCell"'
                        f' style="font-size:12px;{mono}">'
                        f"{r.msg}</td></tr>"
                    )
                    yield {"event": "log-entry", "data": row_html}
                last_seq = current_seq
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


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
