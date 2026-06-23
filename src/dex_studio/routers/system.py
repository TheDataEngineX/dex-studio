"""System domain routes — status, logs (SSE), metrics, components."""

from __future__ import annotations

import asyncio
import calendar
import contextlib
import datetime as _dt
import json
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from dex_studio.config import load_prefs as _load_prefs
from dex_studio.logstore import log_store
from dex_studio.routers._deps import ReadDep, WriteDep, base_ctx, flash, render, stub_page
from dex_studio.scheduler import (
    get_scheduler_status,
    scheduler_clear_dead_letter,
    scheduler_pause,
    scheduler_resume,
    scheduler_trigger,
)
from dex_studio.studio_db import get_studio_db
from dex_studio.utils import fmt_run_row, fmt_ts_iso

router = APIRouter()
log = structlog.get_logger().bind(src="router.system")


def _fmt_uptime(secs: float) -> str:
    days, rem = divmod(int(secs), 86400)
    hours, rem2 = divmod(rem, 3600)
    mins = rem2 // 60
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


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


def _build_recent_runs(eng: Any) -> list[dict[str, Any]]:
    """Return last 20 runs from StudioDb, falling back to engine store."""
    rows: list[dict[str, Any]] = []
    sdb = get_studio_db(eng)
    if sdb is not None:
        for r in sdb.get_runs(None, limit=20):
            raw_st = r.get("status", "")
            st = "failed" if raw_st == "failure" else raw_st
            dur_s = r.get("duration_s")
            if dur_s is None:
                dur_str = "—"
            elif dur_s >= 1:
                dur_str = f"{dur_s:.1f}s"
            else:
                dur_str = f"{int(dur_s * 1000)}ms"
            ts = r.get("finished_at") or r.get("started_at") or ""
            rows.append(
                {
                    "type": "pipeline",
                    "name": r.get("pipeline", "—"),
                    "status": st if st in ("success", "error", "failed", "running") else "error",
                    "status_class": "ok" if st == "success" else "error",
                    "started": fmt_ts_iso(ts),
                    "duration": dur_str,
                    "error": r.get("error") or "",
                    "io": "—",
                    "trigger": r.get("triggered_by") or "scheduler",
                }
            )
    if not rows:
        for r in reversed(eng.store.get_pipeline_runs()[-20:]):
            row = fmt_run_row(r, trigger="manual", io=f"{r.rows_output:,} rows")
            row["status_class"] = "ok" if r.success else "error"
            rows.append(row)
    return rows


def _sys_metrics() -> dict[str, Any]:
    """Read live CPU%, RAM, and uptime via psutil (Linux / macOS / Windows)."""
    import time as _time

    import psutil

    metrics: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        vm = psutil.virtual_memory()
        metrics["mem_used_gb"] = round(vm.used / 1_073_741_824, 1)
        metrics["mem_total_gb"] = round(vm.total / 1_073_741_824, 1)
        metrics["mem_pct"] = round(vm.percent, 1)
    with contextlib.suppress(Exception):
        metrics["cpu_pct"] = round(psutil.cpu_percent(interval=0.2), 1)
    with contextlib.suppress(Exception):
        metrics["uptime_str"] = _fmt_uptime(_time.time() - psutil.boot_time())
    return metrics


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/status", response_class=HTMLResponse)
def system_status(request: Request, eng: ReadDep) -> HTMLResponse:
    log.debug("system status viewed")
    health = eng.health()
    overall = health.get("status", "unknown")
    request.state._health_cache = health
    components = _parse_components(health)
    if overall in ("ok", "healthy"):
        log.info("engine health ok", components=len(components))
    else:
        log.warning("engine health degraded", status=overall, components=len(components))

    dead_letter_count, recent_failure_count = _pipeline_health_overlay(eng)
    if (dead_letter_count > 0 or recent_failure_count > 0) and overall in ("ok", "healthy"):
        overall = "degraded"
    is_healthy, health_class, health_label = _health_banner(
        overall, dead_letter_count, recent_failure_count
    )

    # App version
    app_version = "—"
    try:
        from importlib.metadata import version as _pkg_version

        app_version = _pkg_version("dex-studio")
    except Exception as exc:
        log.debug("could not read app version", error=str(exc))

    # Recent runs list for hub panels and activity feed
    recent_runs_list: list[dict[str, Any]] = []
    try:
        recent_runs_list = _build_recent_runs(eng)
    except Exception as exc:
        log.warning("failed to load recent runs for dashboard", error=str(exc))

    # Scheduler overview for hub panel
    scheduler_overview: dict[str, Any] | None = None
    try:
        sched_status = get_scheduler_status(eng, request.app)
        scheduler_overview = {
            "enabled": sched_status.get("enabled", False),
            "paused": sched_status.get("paused", False),
            "pipeline_count": len(sched_status.get("pipelines", [])),
            "dead_letter_count": len(sched_status.get("dead_letter", [])),
        }
    except Exception as exc:
        log.warning("failed to load scheduler overview", error=str(exc))

    # Log entry count for storage panel
    log_entry_count = log_store.seq

    ctx = base_ctx(request) | {
        "health": health,
        "components": components,
        "is_healthy": is_healthy,
        "health_class": health_class,
        "health_label": health_label,
        "app_version": app_version,
        "recent_runs_list": recent_runs_list,
        "scheduler_overview": scheduler_overview,
        "log_entry_count": log_entry_count,
        **_sys_metrics(),
    }
    return render(request, "system/status.html", ctx)


# ── Logs ──────────────────────────────────────────────────────────────────────


@router.get("/logs", response_class=HTMLResponse)
def system_logs(request: Request, _: ReadDep) -> HTMLResponse:
    log.debug("logs page viewed")
    records = log_store.recent(limit=500)
    log_rows = [{"ts": r.ts, "level": r.level, "logger": r.logger, "msg": r.msg} for r in records]
    ctx = base_ctx(request) | {
        "logs": log_rows,
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
    }
    return render(request, "system/logs.html", ctx)


@router.get("/logs/stream")
def logs_stream(request: Request, _: ReadDep) -> EventSourceResponse:
    """SSE endpoint — streams all structlog entries as JSON (no server-side level filter)."""
    last_seq = log_store.seq

    async def event_generator() -> Any:
        nonlocal last_seq
        while True:
            if await request.is_disconnected():
                break
            new_records = log_store.since(last_seq)
            if new_records:
                last_seq = new_records[-1].seq
                for r in new_records:
                    yield {
                        "data": json.dumps(
                            {"ts": r.ts, "level": r.level, "logger": r.logger, "msg": r.msg}
                        )
                    }
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


# ── Metrics ───────────────────────────────────────────────────────────────────


@router.get("/metrics-live")
async def system_metrics_live(_: ReadDep) -> Any:
    """JSON — live CPU%, MEM% for the Dex AI pane and rail footer polling."""
    from fastapi.responses import JSONResponse

    m = _sys_metrics()
    return JSONResponse(
        {
            "cpu_pct": m.get("cpu_pct", 0.0),
            "mem_pct": m.get("mem_pct", 0.0),
            "mem_used_gb": m.get("mem_used_gb", 0.0),
            "mem_total_gb": m.get("mem_total_gb", 0.0),
            "uptime_str": m.get("uptime_str", "—"),
        }
    )


@router.get("/metrics", response_class=HTMLResponse)
def system_metrics(request: Request, eng: ReadDep) -> HTMLResponse:
    stats = eng.pipeline_stats()
    models = eng.model_registry.list_models()
    lineage_count = len(eng.lineage.all_events) if eng.lineage else 0
    sys = _sys_metrics()
    ctx = base_ctx(request) | {
        "pipeline_total": stats.get("total", 0),
        "pipeline_scheduled": stats.get("scheduled", 0),
        "pipeline_failed": stats.get("failed", 0),
        "model_count": len(models),
        "agent_count": len(eng.agents),
        "lineage_events": lineage_count,
        **sys,
    }
    return render(request, "system/metrics.html", ctx)


# ── Components ────────────────────────────────────────────────────────────────

_COMPONENT_ICONS: dict[str, str] = {
    "duckdb": "database",
    "iceberg": "layers",
    "iceberg_rest": "layers",
    "minio": "archive",
    "s3": "archive",
    "redis": "server",
    "worker_pool": "cpu",
    "worker": "cpu",
    "kafka": "radio",
    "kafka_embedded": "radio",
    "privacy_guard": "shield",
    "schema_registry": "book-open",
    "model_registry": "box",
    "vector_store": "grid-3x3",
    "lineage": "git-branch",
    "ai": "bot",
    "llm": "bot",
    "store": "database",
    "data_store": "database",
    "sqlite": "database",
    "scheduler": "clock",
}


@router.get("/components", response_class=HTMLResponse)
def system_components(request: Request, eng: ReadDep) -> HTMLResponse:
    health = eng.health()
    request.state._health_cache = health

    components: list[dict[str, Any]] = []
    for raw_name, val in health.get("components", {}).items():
        available = bool(val) if not isinstance(val, bool) else val
        components.append(
            {
                "name": raw_name.replace("_", " ").title(),
                "raw_name": raw_name,
                "icon": _COMPONENT_ICONS.get(raw_name, "box"),
                "available": available,
                "status": "ok" if available else "offline",
                "message": "" if available else "Not initialized",
            }
        )

    healthy_count = sum(1 for c in components if c["available"])

    config_entries: list[tuple[str, str]] = []
    try:
        cfg = eng.config
        config_entries = [
            ("project.name", cfg.project.name),
            ("project.version", str(getattr(cfg.project, "version", "—"))),
            ("data.engine", str(getattr(cfg.data, "engine", "duckdb"))),
            ("data.sources", str(len(cfg.data.sources or {}))),
            ("data.pipelines", str(len(cfg.data.pipelines or {}))),
            ("config.path", str(getattr(eng, "config_path", "—"))),
        ]
    except Exception as exc:
        log.warning("failed to read config entries", error=str(exc))

    recent_events: list[dict[str, str]] = []
    try:
        for r in log_store.recent(limit=10):
            recent_events.append(
                {"ts": fmt_ts_iso(str(r.ts)), "level": r.level.lower(), "msg": r.msg}
            )
    except Exception as exc:
        log.warning("failed to load recent events", error=str(exc))

    ctx = base_ctx(request) | {
        "components": components,
        "healthy_count": healthy_count,
        "total_count": len(components),
        "is_healthy": health.get("status") in ("ok", "healthy"),
        "config_entries": config_entries,
        "recent_events": recent_events,
        **_sys_metrics(),
    }
    return render(request, "system/components.html", ctx)


# ── Runs ──────────────────────────────────────────────────────────────────────


@router.get("/runs", response_class=HTMLResponse)
def system_runs(request: Request, eng: ReadDep) -> HTMLResponse:
    """Unified run history — pipelines, transforms, workflows, agents, streams."""
    stats = eng.pipeline_stats()
    runs: list[dict[str, Any]] = []
    try:
        sdb = get_studio_db(eng)
        if sdb is not None:
            for r in sdb.get_runs(None, limit=200):
                raw_st = r.get("status", "")
                st = "failed" if raw_st == "failure" else raw_st
                dur_s = r.get("duration_s")
                dur_str = (
                    "—"
                    if dur_s is None
                    else (f"{dur_s:.1f}s" if dur_s >= 1 else f"{int(dur_s * 1000)}ms")
                )
                ts = r.get("finished_at") or r.get("started_at") or ""
                runs.append(
                    {
                        "type": "pipeline",
                        "name": r.get("pipeline", "—"),
                        "status": st
                        if st in ("success", "error", "failed", "running")
                        else "error",
                        "status_class": "ok" if st == "success" else "error",
                        "started": fmt_ts_iso(ts),
                        "duration": dur_str,
                        "trigger": r.get("triggered_by") or "scheduler",
                        "error": r.get("error") or "",
                        "io": "—",
                    }
                )
        if not runs:
            for r in reversed(eng.store.get_pipeline_runs()[-200:]):
                runs.append(fmt_run_row(r, trigger="manual", io=f"{r.rows_output:,} rows"))
    except Exception as exc:
        log.warning("failed to load run history", error=str(exc))
    ctx = base_ctx(request) | {
        "runs": runs,
        "total_count": len(runs),
        "running_count": stats.get("running", 0),
        "failed_count": stats.get("failed", 0),
        "type_options": ["all", "pipeline", "transform", "workflow", "agent", "stream"],
        "status_options": ["all", "running", "success", "error", "cancelled"],
    }
    return render(request, "system/runs.html", ctx)


# ── Scheduler ─────────────────────────────────────────────────────────────────


@router.get("/scheduler", response_class=HTMLResponse)
def scheduler_page(request: Request, eng: ReadDep) -> HTMLResponse:
    log.debug("scheduler page viewed")
    status = get_scheduler_status(eng, request.app)

    # Build DAG JSON for JS rendering (pipeline dependency graph)
    dag_nodes: list[dict[str, Any]] = []
    for p in status.get("pipelines", []):
        dag_nodes.append(
            {
                "name": p["name"],
                "depends_on": p.get("depends_on", []),
                "status": p.get("status", "never"),
                "schedule": p.get("schedule", ""),
            }
        )

    ctx = base_ctx(request) | {
        "scheduler": status,
        "dag_json": json.dumps(dag_nodes),
        "scheduler_pipeline_data_json": json.dumps(status.get("pipelines", [])),
    }
    return render(request, "system/scheduler.html", ctx)


@router.get("/scheduler/status")
def scheduler_status_api(request: Request, eng: ReadDep) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(get_scheduler_status(eng, request.app))


@router.post("/scheduler/pause")
def scheduler_pause_route(request: Request, eng: WriteDep) -> RedirectResponse:
    scheduler_pause(eng)
    log.info("scheduler paused via UI")
    return RedirectResponse("/system/scheduler", status_code=303)


@router.post("/scheduler/resume")
def scheduler_resume_route(request: Request, eng: WriteDep) -> RedirectResponse:
    scheduler_resume(eng)
    log.info("scheduler resumed via UI")
    return RedirectResponse("/system/scheduler", status_code=303)


@router.post("/scheduler/trigger/{name}")
def scheduler_trigger_route(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    status = scheduler_trigger(eng, name)
    log.info("manual pipeline trigger", pipeline=name, status=status)
    return RedirectResponse("/system/scheduler", status_code=303)


@router.post("/scheduler/dead-letter/{name}/clear")
def scheduler_dead_letter_clear(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    scheduler_clear_dead_letter(eng, name)
    log.info("dead letter cleared via UI", pipeline=name)
    return RedirectResponse("/system/scheduler", status_code=303)


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
    budget = _load_prefs().monthly_budget_usd
    providers = [
        {
            "name": k,
            "spend": round(v, 4),
            "share": round(v / spend_total, 4) if spend_total else 0.0,
        }
        for k, v in sorted(provider_map.items(), key=lambda kv: kv[1], reverse=True)
    ]
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
    }
    return render(request, "system/costs.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────


_SYSTEM_STUB_TITLES = {
    "/system/traces": "System Traces",
    "/system/activity": "Activity Log",
    "/system/incidents": "Incidents",
    "/system/connection": "Connection Pool",
}


# ── Compaction ────────────────────────────────────────────────────────────────


def _get_compaction_deps(eng: Any) -> tuple[Any, Any] | None:
    """Return (CompactionEngine, StudioDb) or None if unavailable."""
    from dex_studio.compaction import CompactionEngine
    from dex_studio.scheduler import _get_or_create_studio_db

    db = _get_or_create_studio_db(eng)
    if db is None:
        return None
    return CompactionEngine(eng.project_dir, db), db


@router.get("/compaction", response_class=HTMLResponse)
def compaction_page(request: Request, eng: ReadDep) -> HTMLResponse:
    deps = _get_compaction_deps(eng)
    runs: list[dict[str, Any]] = []
    pipelines = list((eng.config.data.pipelines or {}).keys())
    if deps:
        _, db = deps
        runs = db.get_compaction_runs(limit=50)
    ctx = base_ctx(request) | {
        "runs": runs,
        "pipelines": pipelines,
    }
    return render(request, "system/compaction.html", ctx)


@router.post("/compaction/run/{pipeline}")
def compaction_run(request: Request, eng: WriteDep, pipeline: str) -> RedirectResponse:
    deps = _get_compaction_deps(eng)
    if deps:
        engine, _ = deps
        result = engine.compact_pipeline(pipeline)
        if result:
            pct = round(result.savings_pct, 1)
            from dex_studio.routers._deps import flash

            msg = f"Compacted '{pipeline}': {result.files_before}→1 files, {pct}% smaller."
            flash(request, msg)
        else:
            from dex_studio.routers._deps import flash

            flash(request, f"Nothing to compact for '{pipeline}' (< 2 files).")
    return RedirectResponse("/system/compaction", status_code=303)


@router.post("/compaction/run-all")
def compaction_run_all(request: Request, eng: WriteDep) -> RedirectResponse:
    deps = _get_compaction_deps(eng)
    if deps:
        engine, _ = deps
        pipelines = list((eng.config.data.pipelines or {}).keys())
        results = engine.compact_all(pipelines)
        from dex_studio.routers._deps import flash

        flash(request, f"Compaction complete: {len(results)} pipeline(s) compacted.")
    return RedirectResponse("/system/compaction", status_code=303)


# ── Alerting ──────────────────────────────────────────────────────────────────


def _get_alerting_deps(eng: Any) -> tuple[Any, Any] | None:
    from dex_studio.alerting import AlertDispatcher, read_alerting_config
    from dex_studio.scheduler import _get_or_create_studio_db

    db = _get_or_create_studio_db(eng)
    if db is None:
        return None
    cfg = read_alerting_config(eng)
    return AlertDispatcher(db, cfg), db


@router.get("/alerting", response_class=HTMLResponse)
def alerting_page(request: Request, eng: ReadDep) -> HTMLResponse:
    deps = _get_alerting_deps(eng)
    alerts: list[dict[str, Any]] = []
    freshness: list[dict[str, Any]] = []
    if deps:
        _, db = deps
        alerts = db.get_alerts(limit=100)
        from dex_studio.alerting import FreshnessChecker

        pipelines: dict[str, Any] = eng.config.data.pipelines or {}
        freshness = FreshnessChecker(db, pipelines).check_all()
    ctx = base_ctx(request) | {
        "alerts": alerts,
        "freshness": freshness,
        "undelivered": sum(1 for a in alerts if not a["delivered"]),
    }
    return render(request, "system/alerting.html", ctx)


@router.post("/alerting/dispatch")
def alerting_dispatch(request: Request, eng: WriteDep) -> RedirectResponse:
    deps = _get_alerting_deps(eng)
    if deps:
        dispatcher, _ = deps
        n = dispatcher.dispatch_pending()
        from dex_studio.routers._deps import flash

        flash(request, f"Dispatched {n} pending alert(s).")
    return RedirectResponse("/system/alerting", status_code=303)


@router.post("/reload-config")
def reload_config(request: Request, eng: WriteDep) -> RedirectResponse:
    """Re-read dex.yaml from disk and reinitialize the engine in-place."""
    from dex_studio._engine import init_engine

    try:
        init_engine(str(getattr(eng, "config_path", "")))
        request.session["flash"] = {"msg": "Config reloaded from disk.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": f"Reload failed: {exc}", "kind": "error"}
    return RedirectResponse("/system/components", status_code=303)


@router.get("/traces", response_class=HTMLResponse)
@router.get("/activity", response_class=HTMLResponse)
@router.get("/incidents", response_class=HTMLResponse)
@router.get("/connection", response_class=HTMLResponse)
def system_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _SYSTEM_STUB_TITLES)


# ── Settings ──────────────────────────────────────────────────────────────────


def _write_and_reload_config(config_path: Path, raw: dict[str, Any]) -> str | None:
    """Write YAML config to disk and reload engine. Returns error message or None."""
    import yaml

    try:
        config_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False)
        )
        log.info("dex.yaml settings saved", path=str(config_path))
    except Exception as exc:
        log.error("failed to write dex.yaml settings", error=str(exc))
        return str(exc)
    try:
        from dex_studio._engine import init_engine

        init_engine(str(config_path))
        log.info("engine reloaded after settings save")
    except Exception as exc:
        log.warning("settings saved but engine reload failed", error=str(exc))
    return None


def _load_yaml_config(eng: Any) -> dict[str, Any]:
    import yaml

    config_path = getattr(eng, "config_path", None)
    if not config_path:
        return {}
    try:
        return yaml.safe_load(Path(str(config_path)).read_text()) or {}
    except Exception as exc:
        log.warning("could not read dex.yaml for settings", error=str(exc))
        return {}


@router.get("/settings", response_class=HTMLResponse)
def system_settings(request: Request, eng: ReadDep) -> HTMLResponse:
    raw = _load_yaml_config(eng)
    project = raw.get("project", {}) or {}
    scheduler = raw.get("scheduler", {}) or {}
    retry = scheduler.get("retry", {}) or {}
    ai_cfg = raw.get("ai", {}) or {}
    llm = ai_cfg.get("llm", {}) or {}
    retrieval = ai_cfg.get("retrieval", {}) or {}
    secops = raw.get("secops", {}) or {}
    pii = secops.get("pii", {}) or {}
    audit = secops.get("audit", {}) or {}
    guard = secops.get("guard", {}) or {}
    obs = raw.get("observability", {}) or {}

    ctx = base_ctx(request) | {
        "config_path": str(getattr(eng, "config_path", "")) or "",
        "proj_name": str(project.get("name", "")),
        "proj_version": str(project.get("version", "")),
        "proj_description": str(project.get("description", "")),
        "sched_enabled": bool(scheduler.get("enabled", True)),
        "sched_timezone": str(scheduler.get("timezone", "UTC")),
        "sched_max_concurrent": int(scheduler.get("max_concurrent_pipelines", 3)),
        "sched_retry_attempts": int(retry.get("max_attempts", 3)),
        "sched_retry_backoff": int(retry.get("backoff_seconds", 60)),
        "llm_provider": str(llm.get("provider", "ollama")),
        "llm_model": str(llm.get("model", "")),
        "llm_host": str(llm.get("host", "")),
        "ret_strategy": str(retrieval.get("strategy", "hybrid")),
        "ret_top_k": int(retrieval.get("top_k", 10)),
        "ret_reranker": bool(retrieval.get("reranker", False)),
        "pii_scan": bool(pii.get("scan", False)),
        "audit_enabled": bool(audit.get("enabled", False)),
        "guard_enabled": bool(guard.get("enabled", False)),
        "guard_block_on_detect": bool(guard.get("block_on_detect", False)),
        "guard_log_all_outbound": bool(guard.get("log_all_outbound", False)),
        "obs_metrics": bool(obs.get("metrics", True)),
        "obs_tracing": bool(obs.get("tracing", True)),
        "obs_log_level": str(obs.get("log_level", "INFO")),
    }
    return render(request, "system/settings.html", ctx)


@router.post("/settings", response_class=HTMLResponse)
async def system_settings_save(request: Request, eng: WriteDep) -> RedirectResponse:
    import yaml

    form = await request.form()
    config_path = Path(str(getattr(eng, "config_path", "") or ""))
    if not config_path or not config_path.exists():
        flash(request, "No config file found.", "error")
        return RedirectResponse("/system/settings", status_code=303)

    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except Exception as exc:
        log.error("failed to read dex.yaml for settings save", error=str(exc))
        flash(request, f"Could not read config: {exc}", "error")
        return RedirectResponse("/system/settings", status_code=303)

    def _bool(key: str) -> bool:
        return str(form.get(key, "")).lower() in ("on", "true", "1", "yes")

    def _int(key: str, default: int) -> int:
        try:
            val = form.get(key)
            return int(str(val)) if val is not None else default
        except (ValueError, TypeError):
            return default

    raw.setdefault("project", {})
    raw["project"]["name"] = str(form.get("proj_name", raw["project"].get("name", "")))
    raw["project"]["version"] = str(form.get("proj_version", raw["project"].get("version", "")))
    raw["project"]["description"] = str(
        form.get("proj_description", raw["project"].get("description", ""))
    )

    raw.setdefault("scheduler", {})
    raw["scheduler"]["enabled"] = _bool("sched_enabled")
    raw["scheduler"]["timezone"] = str(form.get("sched_timezone", "UTC"))
    raw["scheduler"]["max_concurrent_pipelines"] = _int("sched_max_concurrent", 3)
    raw["scheduler"].setdefault("retry", {})
    raw["scheduler"]["retry"]["max_attempts"] = _int("sched_retry_attempts", 3)
    raw["scheduler"]["retry"]["backoff_seconds"] = _int("sched_retry_backoff", 60)

    raw.setdefault("ai", {})
    raw["ai"].setdefault("llm", {})
    raw["ai"]["llm"]["provider"] = str(form.get("llm_provider", "ollama"))
    raw["ai"]["llm"]["model"] = str(form.get("llm_model", ""))
    host = str(form.get("llm_host", "")).strip()
    if host:
        raw["ai"]["llm"]["host"] = host
    else:
        raw["ai"]["llm"].pop("host", None)

    raw["ai"].setdefault("retrieval", {})
    raw["ai"]["retrieval"]["strategy"] = str(form.get("ret_strategy", "hybrid"))
    raw["ai"]["retrieval"]["top_k"] = _int("ret_top_k", 10)
    raw["ai"]["retrieval"]["reranker"] = _bool("ret_reranker")

    raw.setdefault("secops", {})
    raw["secops"].setdefault("pii", {})
    raw["secops"]["pii"]["scan"] = _bool("pii_scan")
    raw["secops"].setdefault("audit", {})
    raw["secops"]["audit"]["enabled"] = _bool("audit_enabled")
    raw["secops"].setdefault("guard", {})
    raw["secops"]["guard"]["enabled"] = _bool("guard_enabled")
    raw["secops"]["guard"]["block_on_detect"] = _bool("guard_block_on_detect")
    raw["secops"]["guard"]["log_all_outbound"] = _bool("guard_log_all_outbound")

    raw.setdefault("observability", {})
    raw["observability"]["metrics"] = _bool("obs_metrics")
    raw["observability"]["tracing"] = _bool("obs_tracing")
    raw["observability"]["log_level"] = str(form.get("obs_log_level", "INFO"))

    err = _write_and_reload_config(config_path, raw)
    if err:
        flash(request, f"Save failed: {err}", "error")
        return RedirectResponse("/system/settings", status_code=303)

    flash(request, "Settings saved and config reloaded.", "success")
    return RedirectResponse("/system/settings", status_code=303)
