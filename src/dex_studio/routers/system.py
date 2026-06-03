"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio.logstore import log_store
from dex_studio.routers._deps import base_ctx, get_eng, render, stub_page
from dex_studio.routers._deps import require_auth as _require_auth
from dex_studio.routers._deps import require_engine as _require_engine

router = APIRouter()


def _guard(request: Request) -> RedirectResponse | None:
    """Auth + engine check without CSRF — read-only routes only."""
    return _require_auth(request) or _require_engine()


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


# ── Runs ──────────────────────────────────────────────────────────────────────


@router.get("/runs", response_class=HTMLResponse)
async def system_runs(
    request: Request,
    type: str = "all",
    status: str = "all",
) -> HTMLResponse:
    """Unified run history — pipelines, transforms, workflows, agents, streams."""
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    stats = eng.pipeline_stats()
    runs: list[dict[str, Any]] = []
    # Read directly from pipeline_runs.json (authoritative run store)
    runs_path = eng.project_dir / ".dex" / "pipeline_runs.json"
    with contextlib.suppress(Exception):
        raw_runs: list[dict[str, Any]] = _json.loads(runs_path.read_text())
        for r in reversed(raw_runs[-200:]):
            run_status = "success" if r.get("success") else "error"
            dur_ms = float(r.get("duration_ms", 0))
            dur_str = f"{dur_ms / 1000:.1f}s" if dur_ms >= 1000 else f"{int(dur_ms)}ms"
            ts = str(r.get("timestamp", ""))[:19].replace("T", " ")
            runs.append(
                {
                    "type": "pipeline",
                    "name": r.get("pipeline_name", "unknown"),
                    "status": run_status,
                    "started": ts,
                    "duration": dur_str,
                    "trigger": "manual",
                    "io": f"{r.get('rows_output', 0):,} rows",
                }
            )
    # Apply server-side filters (type + status route params preserved for deep-link).
    type_options = ["all", "pipeline", "transform", "workflow", "agent", "stream"]
    status_options = ["all", "running", "success", "error", "cancelled"]
    total_runs = len(runs)
    filter_type = type
    filter_status = status
    if filter_type != "all":
        runs = [r for r in runs if r["type"] == filter_type]
    if filter_status != "all":
        runs = [r for r in runs if r["status"] == filter_status]
    ctx = base_ctx(request) | {
        "runs": runs,
        "total_count": total_runs,
        "running_count": stats.get("running", 0),
        "failed_count": stats.get("failed", 0),
        "filter_type": filter_type,
        "filter_status": filter_status,
        "type_options": type_options,
        "status_options": status_options,
    }
    return render(request, "system/runs.html", ctx)


# ── Costs ─────────────────────────────────────────────────────────────────────


@router.get("/costs", response_class=HTMLResponse)
async def system_costs(request: Request) -> HTMLResponse:
    """External API spend — per-provider breakdown.

    Populated by the AuditLogger / cost-tracking subsystem once available
    (dex ≥ 0.5). Until then, renders a zero-state scaffold.
    """
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    # Pull spend data from audit events when available.
    audit = getattr(eng, "secops_audit", None)
    events = audit.events if audit is not None else []
    # Aggregate cost by provider from outbound events (schema: event.metadata["provider"]).
    provider_map: dict[str, float] = {}
    for ev in events:
        md = getattr(ev, "metadata", {}) or {}
        prov = md.get("provider", "")
        cost = float(md.get("cost_usd", 0.0))
        if prov and cost:
            provider_map[prov] = provider_map.get(prov, 0.0) + cost
    spend_total = sum(provider_map.values())
    budget = 25.0
    providers = [
        {
            "name": k,
            "spend": round(v, 4),
            "share": round(v / spend_total, 4) if spend_total else 0.0,
        }
        for k, v in sorted(provider_map.items(), key=lambda kv: kv[1], reverse=True)
    ]
    import datetime as _dt

    _now = _dt.datetime.now()
    ctx = base_ctx(request) | {
        "spend_total": round(spend_total, 4),
        "budget": budget,
        "budget_pct": round(min(spend_total / budget * 100, 100), 1) if budget else 0.0,
        "providers": providers,
        "breakdown": [],
        "month_label": _now.strftime("%B %Y"),
        "month_day": _now.day,
        "month_days": (_dt.date(_now.year, _now.month % 12 + 1, 1) - _dt.timedelta(days=1)).day,
    }
    return render(request, "system/costs.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────


_SYSTEM_STUB_TITLES = {
    "/system/traces": "System Traces",
    "/system/activity": "Activity Log",
    "/system/incidents": "Incidents",
    "/system/settings": "Settings",
    "/system/connection": "Connection Pool",
}


@router.get("/traces", response_class=HTMLResponse)
@router.get("/activity", response_class=HTMLResponse)
@router.get("/incidents", response_class=HTMLResponse)
@router.get("/settings", response_class=HTMLResponse)
@router.get("/connection", response_class=HTMLResponse)
async def system_stub(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    return stub_page(request, _SYSTEM_STUB_TITLES)
