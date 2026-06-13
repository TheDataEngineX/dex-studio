"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
import contextlib
from html import escape as _html_escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio.logstore import log_store
from dex_studio.routers._deps import ReadDep, base_ctx, render, stub_page

router = APIRouter()

_cpu_last: tuple[float, float] = (0.0, 0.0)  # (total, idle) at last sample


def _sys_metrics() -> dict[str, Any]:
    """Read live CPU%, RAM, and uptime from /proc — no extra deps."""
    global _cpu_last
    metrics: dict[str, Any] = {}
    # ── RAM ──────────────────────────────────────────────────────────────────
    with contextlib.suppress(Exception):
        meminfo = Path("/proc/meminfo").read_text()
        mem: dict[str, int] = {}
        for line in meminfo.splitlines():
            parts = line.split()
            if parts[0].rstrip(":") in ("MemTotal", "MemAvailable"):
                mem[parts[0].rstrip(":")] = int(parts[1])
        total_kb = mem.get("MemTotal", 0)
        avail_kb = mem.get("MemAvailable", 0)
        used_kb = total_kb - avail_kb
        metrics["mem_used_gb"] = round(used_kb / 1_048_576, 1)
        metrics["mem_total_gb"] = round(total_kb / 1_048_576, 1)
        metrics["mem_pct"] = round(used_kb / total_kb * 100, 1) if total_kb else 0.0
    # ── CPU (delta since last call) ───────────────────────────────────────────
    with contextlib.suppress(Exception):
        stat_line = Path("/proc/stat").read_text().splitlines()[0]
        vals = [int(x) for x in stat_line.split()[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        prev_total, prev_idle = _cpu_last
        d_total = total - prev_total
        d_idle = idle - prev_idle
        _cpu_last = (total, idle)
        metrics["cpu_pct"] = round((1.0 - d_idle / d_total) * 100, 1) if d_total else 0.0
    # ── Uptime ────────────────────────────────────────────────────────────────
    with contextlib.suppress(Exception):
        uptime_secs = float(Path("/proc/uptime").read_text().split()[0])
        days, rem = divmod(int(uptime_secs), 86400)
        hours, rem2 = divmod(rem, 3600)
        mins = rem2 // 60
        if days:
            metrics["uptime_str"] = f"{days}d {hours}h {mins}m"
        elif hours:
            metrics["uptime_str"] = f"{hours}h {mins}m"
        else:
            metrics["uptime_str"] = f"{mins}m"
    return metrics


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/status", response_class=HTMLResponse)
def system_status(request: Request, eng: ReadDep) -> HTMLResponse:
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
        **_sys_metrics(),
    }
    return render(request, "system/status.html", ctx)


# ── Logs ──────────────────────────────────────────────────────────────────────


@router.get("/logs", response_class=HTMLResponse)
def system_logs(request: Request, _: ReadDep, level: str = "INFO") -> HTMLResponse:
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
def logs_stream(request: Request, _: ReadDep, level: str = "INFO") -> EventSourceResponse:
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
                    lc = _html_escape(r.level.lower())
                    row_html = (
                        f"<tr>"
                        f'<td class="mono" style="font-size:11px;white-space:nowrap">'
                        f"{_html_escape(r.ts)}</td>"
                        f"<td>"
                        f'<span class="dex-log-badge dex-log-{lc}">'
                        f"{_html_escape(r.level)}</span></td>"
                        f'<td class="mono" style="font-size:12px">'
                        f"{_html_escape(r.msg)}</td></tr>"
                    )
                    yield {"event": "log-entry", "data": row_html}
                last_seq = current_seq
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


# ── Metrics ───────────────────────────────────────────────────────────────────


@router.get("/metrics", response_class=HTMLResponse)
def system_metrics(request: Request, eng: ReadDep) -> HTMLResponse:
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
def system_components(request: Request, eng: ReadDep) -> HTMLResponse:
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
def system_runs(
    request: Request,
    eng: ReadDep,
    type: str = "all",
    status: str = "all",
) -> HTMLResponse:
    """Unified run history — pipelines, transforms, workflows, agents, streams."""
    stats = eng.pipeline_stats()
    runs: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for r in reversed(eng.store.get_pipeline_runs()[-200:]):
            dur_ms = r.duration_ms
            dur_str = f"{dur_ms / 1000:.1f}s" if dur_ms >= 1000 else f"{int(dur_ms)}ms"
            ts = str(r.timestamp)[:19].replace("T", " ")
            runs.append(
                {
                    "type": "pipeline",
                    "name": r.pipeline_name,
                    "status": "success" if r.success else "error",
                    "started": ts,
                    "duration": dur_str,
                    "trigger": "manual",
                    "io": f"{r.rows_output:,} rows",
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
def system_costs(request: Request, eng: ReadDep) -> HTMLResponse:
    """External API spend — per-provider breakdown.

    Populated by the AuditLogger / cost-tracking subsystem once available
    (dex ≥ 0.5). Until then, renders a zero-state scaffold.
    """
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
def system_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _SYSTEM_STUB_TITLES)
