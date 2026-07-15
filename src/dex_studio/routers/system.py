"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
import calendar
import contextlib
from html import escape as _html_escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio._engine import init_engine
from dex_studio.logstore import log_store
from dex_studio.routers._deps import JsonReadDep, ReadDep, WriteDep, base_ctx, flash, render
from dex_studio.studio_db import get_studio_db
from dex_studio.utils import fmt_ts_iso

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


def _parse_components(health: dict[str, Any]) -> list[dict[str, Any]]:
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
    return components


def _health_banner(overall: str, dead: int, failures: int) -> tuple[bool, str, str]:
    is_healthy = overall in ("ok", "healthy")
    health_class = "ok" if is_healthy else ("warn" if overall == "degraded" else "error")
    if dead > 0:
        label = f"{dead} pipeline(s) dead-lettered — check scheduler"
    elif failures > 0:
        label = f"{failures} recent pipeline failure(s)"
    elif is_healthy:
        label = "All Systems Operational"
    elif overall == "degraded":
        label = "System Degraded"
    else:
        label = "System Error — Check Components"
    return is_healthy, health_class, label


def _pipeline_health_overlay(eng: Any) -> tuple[int, int]:
    """Return (dead_letter_count, recent_failure_count) from StudioDb."""
    dead = 0
    failures = 0
    with contextlib.suppress(Exception):
        sdb = get_studio_db(eng)
        if sdb is not None:
            dead = len(sdb.get_dead_letter())
            recent = sdb.get_runs(None, limit=20)
            failures = sum(
                1 for r in recent if r.get("status", "") in ("failed", "failure", "error")
            )
    return dead, failures


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
    scheduler_overview: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        from dex_studio.scheduler import get_scheduler_status

        sched_raw = get_scheduler_status(eng, request.app)
        scheduler_overview = {
            "enabled": sched_raw.get("enabled", False),
            "paused": sched_raw.get("paused", False),
            "pipeline_count": len(sched_raw.get("pipelines", [])),
            "dead_letter_count": len(sched_raw.get("dead_letter", [])),
        }

    ctx = base_ctx(request) | {
        "health": health,
        "components": components,
        "is_healthy": health.get("status") in ("ok", "healthy"),
        "scheduler_overview": scheduler_overview,
        **_sys_metrics(),
    }
    return render(request, "system/status.html", ctx)


# ── Logs ──────────────────────────────────────────────────────────────────────


@router.get("/logs", response_class=HTMLResponse)
def system_logs(request: Request, _: ReadDep, level: str = "INFO") -> HTMLResponse:
    level_upper = level.upper()
    records = [r for r in log_store.recent(limit=500) if r.level >= level_upper][:200]
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
                records = [
                    r for r in log_store.recent(limit=new_count * 4) if r.level >= level_upper
                ]
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


@router.get("/metrics-live", response_class=JSONResponse)
def system_metrics_live(_request: Request, _eng: JsonReadDep) -> JSONResponse:
    return JSONResponse(_sys_metrics())


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
            ts = fmt_ts_iso(r.timestamp)
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
        "month_days": calendar.monthrange(_now.year, _now.month)[1],
        "costs_config": getattr(getattr(eng.config, "observability", None), "costs", None),
    }
    return render(request, "system/costs.html", ctx)


# ── Compaction ────────────────────────────────────────────────────────────────


@router.get("/compaction", response_class=HTMLResponse)
def system_compaction(request: Request, eng: ReadDep) -> HTMLResponse:
    ctx = base_ctx(request) | {
        "compaction_config": getattr(
            getattr(eng.config, "observability", None), "compaction", None
        ),
    }
    return render(request, "system/compaction.html", ctx)


# ── Alerting ──────────────────────────────────────────────────────────────────


@router.get("/alerting", response_class=HTMLResponse)
def system_alerting(request: Request, eng: ReadDep) -> HTMLResponse:
    ctx = base_ctx(request) | {
        "alerting_config": getattr(getattr(eng.config, "observability", None), "alerting", None),
    }
    return render(request, "system/alerting.html", ctx)


# ── Traces ────────────────────────────────────────────────────────────────────


@router.get("/traces", response_class=HTMLResponse)
def system_traces(request: Request, _: ReadDep, level: str = "INFO") -> HTMLResponse:
    level_upper = level.upper()
    records = [r for r in log_store.recent(limit=500) if r.level >= level_upper][:200]
    ctx = base_ctx(request) | {
        "entries": [{"ts": r.ts, "level": r.level, "msg": r.msg} for r in records],
        "level": level_upper,
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
    }
    return render(request, "system/traces.html", ctx)


# ── Activity ──────────────────────────────────────────────────────────────────


@router.get("/activity", response_class=HTMLResponse)
def system_activity(request: Request, eng: ReadDep) -> HTMLResponse:
    events: list[dict[str, str]] = []
    audit = getattr(eng, "secops_audit", None)
    if audit is not None:
        for ev in getattr(audit, "events", [])[-100:]:
            events.append(
                {
                    "ts": fmt_ts_iso(getattr(ev, "occurred_at", "")),
                    "action": getattr(ev, "operation", ""),
                    "dataset": getattr(ev, "dataset_name", ""),
                    "actor": getattr(ev, "actor", ""),
                }
            )
    if not events:
        for r in reversed(getattr(eng.store, "get_pipeline_runs", lambda: [])()[-50:]):
            ts = fmt_ts_iso(getattr(r, "timestamp", ""))
            events.append(
                {
                    "ts": ts,
                    "action": "pipeline_run",
                    "dataset": getattr(r, "pipeline_name", ""),
                    "actor": "scheduler",
                }
            )
    ctx = base_ctx(request) | {"events": events}
    return render(request, "system/activity.html", ctx)


# ── Incidents ─────────────────────────────────────────────────────────────────


@router.get("/incidents", response_class=HTMLResponse)
def system_incidents(request: Request, eng: ReadDep) -> HTMLResponse:
    dead: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        sdb = get_studio_db(eng)
        if sdb is not None:
            dead = sdb.get_dead_letter()
            recent = sdb.get_runs(None, limit=50)
            failures = [
                {
                    "pipeline": r.get("pipeline", ""),
                    "status": r.get("status", ""),
                    "finished_at": str(r.get("finished_at", "") or ""),
                    "duration_s": r.get("duration_s"),
                }
                for r in recent
                if r.get("status", "") in ("failed", "failure", "error")
            ]
    ctx = base_ctx(request) | {"dead_letter": dead, "failures": failures}
    return render(request, "system/incidents.html", ctx)


# ── Connection Pool ───────────────────────────────────────────────────────────


@router.get("/connection", response_class=HTMLResponse)
def system_connection(request: Request, eng: ReadDep) -> HTMLResponse:
    sources: list[dict[str, str]] = []
    for name, cfg in (getattr(getattr(eng.config, "data", None), "sources", {}) or {}).items():
        sources.append(
            {
                "name": name,
                "type": str(getattr(cfg, "type", "")),
                "path": str(getattr(cfg, "path", "") or getattr(cfg, "url", "") or ""),
                "status": "configured",
            }
        )
    ctx = base_ctx(request) | {"sources": sources}
    return render(request, "system/connection.html", ctx)


# ── Settings ──────────────────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
def system_settings(request: Request, eng: ReadDep) -> HTMLResponse:
    cfg = eng.config
    ai = getattr(cfg, "ai", None)
    sec = getattr(cfg, "secops", None)
    obs = getattr(cfg, "observability", None)
    llm = getattr(ai, "llm", None) if ai else None
    ret = getattr(ai, "retrieval", None) if ai else None
    pii = getattr(sec, "pii", None) if sec else None
    audit = getattr(sec, "audit", None) if sec else None
    guard = getattr(sec, "guard", None) if sec else None
    ctx = base_ctx(request) | {
        "config_path": str(eng.config_path),
        "proj_name": cfg.project.name,
        "proj_version": cfg.project.version,
        "proj_description": cfg.project.description or "",
        "sched_timezone": "UTC",
        "sched_max_concurrent": 3,
        "sched_retry_attempts": 3,
        "sched_retry_backoff": 60,
        "sched_enabled": True,
        "llm_provider": llm.provider if llm else "ollama",
        "llm_model": llm.model if llm else "qwen3:8b",
        "llm_host": getattr(llm, "host", "") if llm else "",
        "ret_strategy": ret.strategy if ret else "hybrid",
        "ret_top_k": ret.top_k if ret else 10,
        "ret_reranker": getattr(ret, "reranker", True) if ret else True,
        "pii_scan": getattr(pii, "scan", False) if pii else False,
        "audit_enabled": getattr(audit, "enabled", False) if audit else False,
        "guard_enabled": getattr(guard, "enabled", True) if guard else False,
        "guard_block_on_detect": getattr(guard, "block_on_detect", False) if guard else False,
        "guard_log_all_outbound": getattr(guard, "log_all_outbound", True) if guard else False,
        "obs_log_level": obs.log_level if obs else "INFO",
        "obs_metrics": obs.metrics if obs else True,
        "obs_tracing": obs.tracing if obs else False,
    }
    return render(request, "system/settings.html", ctx)


@router.post("/settings")
def system_settings_save(
    request: Request,
    eng: WriteDep,
    proj_name: str = Form(""),
    proj_version: str = Form(""),
    proj_description: str = Form(""),
    sched_timezone: str = Form("UTC"),
    sched_max_concurrent: int = Form(3),
    sched_retry_attempts: int = Form(3),
    sched_retry_backoff: int = Form(60),
    sched_enabled: bool = Form(False),
    llm_provider: str = Form("ollama"),
    llm_model: str = Form("qwen3:8b"),
    llm_host: str = Form(""),
    ret_strategy: str = Form("hybrid"),
    ret_top_k: int = Form(10),
    ret_reranker: bool = Form(False),
    pii_scan: bool = Form(False),
    audit_enabled: bool = Form(False),
    guard_enabled: bool = Form(False),
    guard_block_on_detect: bool = Form(False),
    guard_log_all_outbound: bool = Form(False),
    obs_log_level: str = Form("INFO"),
    obs_metrics: bool = Form(False),
    obs_tracing: bool = Form(False),
) -> RedirectResponse:
    eng.config.project.name = proj_name
    eng.config.project.version = proj_version
    eng.config.project.description = proj_description
    ai = getattr(eng.config, "ai", None)
    if ai:
        ai.llm.provider = llm_provider
        ai.llm.model = llm_model
        ai.retrieval.strategy = ret_strategy
        ai.retrieval.top_k = ret_top_k
        ai.retrieval.reranker = ret_reranker
    sec = getattr(eng.config, "secops", None)
    if sec:
        sec.pii.scan = pii_scan
        sec.audit.enabled = audit_enabled
        sec.guard.enabled = guard_enabled
        sec.guard.block_on_detect = guard_block_on_detect
        sec.guard.log_all_outbound = guard_log_all_outbound
    obs = getattr(eng.config, "observability", None)
    if obs:
        obs.log_level = obs_log_level
        obs.metrics = obs_metrics
        obs.tracing = obs_tracing
    eng._save_config()
    init_engine(eng.config_path)
    flash(request, "Settings saved and engine reloaded.")
    return RedirectResponse("/system/settings", status_code=303)
