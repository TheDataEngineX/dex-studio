"""Data domain routes — pipelines, sources, SQL, warehouse, lineage, quality."""

from __future__ import annotations

import contextlib
import datetime
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any

import duckdb
import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio import _json
from dex_studio.flow import build_nodes
from dex_studio.jobs import is_pipeline_running, run_all_pipelines_bg, run_pipeline_bg
from dex_studio.routers._deps import (
    JsonReadDep,
    ReadDep,
    WriteDep,
    base_ctx,
    flash,
    render,
    stub_page,
)
from dex_studio.studio_db import get_studio_db
from dex_studio.utils import fmt_cron, fmt_ts, fmt_ts_iso

router = APIRouter()
log = structlog.get_logger().bind(src="router.data")


def _fmt_dur_s(dur_s: float | None) -> str:
    if dur_s is None:
        return "—"
    return f"{dur_s:.1f}s" if dur_s >= 1 else f"{int(dur_s * 1000)}ms"


def _fmt_dur_ms(dur_ms: float | None) -> str:
    if dur_ms is None:
        return "—"
    return f"{dur_ms / 1000:.1f}s" if dur_ms >= 1000 else f"{int(dur_ms)}ms"


_SOURCE_TYPES = [
    "csv",
    "parquet",
    "delta",
    "duckdb",
    "postgres",
    "mysql",
    "s3",
    "rest",
    "http",
    "sse",
    "kafka",
    "spark",
    "dbt",
]


# ── Dashboard (/data) ────────────────────────────────────────────────────────


def _build_dashboard_recent_runs(eng: Any) -> list[dict[str, Any]]:
    """Return last 5 pipeline runs as display-ready dicts."""
    runs: list[dict[str, Any]] = []
    sdb = get_studio_db(eng)
    if sdb is not None:
        with contextlib.suppress(Exception):
            for r in sdb.get_runs(None, limit=5):
                st = r.get("status", "")
                pipe_name = r.get("pipeline") or "—"
                ts = r.get("finished_at") or r.get("started_at")
                runs.append(
                    {
                        "name": pipe_name,
                        "pipeline": pipe_name,
                        "status": "success" if st == "success" else "error",
                        "status_class": "ok" if st == "success" else "error",
                        "duration": _fmt_dur_s(r.get("duration_s")),
                        "rows": "—",
                        "started": fmt_ts(ts),
                    }
                )
    if not runs:
        with contextlib.suppress(Exception):
            for r in eng.store.get_pipeline_runs()[:5]:
                success = getattr(r, "success", False)
                pipe_name = getattr(r, "pipeline_name", "") or getattr(r, "pipeline", "") or "—"
                runs.append(
                    {
                        "name": pipe_name,
                        "pipeline": pipe_name,
                        "status": "success" if success else "error",
                        "status_class": "ok" if success else "error",
                        "duration": _fmt_dur_ms(getattr(r, "duration_ms", None)),
                        "rows": str(getattr(r, "rows_output", None) or "—"),
                        "started": fmt_ts(getattr(r, "timestamp", None)),
                    }
                )
    return runs


def _build_activity_feed(recent_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthesize an activity feed from recent pipeline runs."""
    feed: list[dict[str, Any]] = []
    for r in recent_runs[:10]:
        status = r.get("status", "error")
        is_ok = status in ("success", "ok")
        feed.append(
            {
                "domain": "data",
                "icon": "check-circle" if is_ok else "alert-circle",
                "desc": f"Pipeline {r.get('name', '—')} {'completed' if is_ok else 'failed'}",
                "sub": r.get("duration", "—"),
                "badge": "OK" if is_ok else "FAIL",
                "href": f"/data/pipelines/{r.get('name', '')}",
                "time_ago": r.get("started", "—"),
            }
        )
    return feed


def _build_quality_summary(eng: Any) -> dict[str, Any]:
    """Return summary quality info: pass_pct (str), failing (list of dicts)."""
    result: dict[str, Any] = {"pass_pct": "—", "failing": []}
    with contextlib.suppress(Exception):
        history = eng.quality_history()
        runs = history.get("runs", [])
        if runs:
            latest = runs[0]
            results = latest.get("results", {})
            scores = []
            failing: list[dict[str, str]] = []
            for table, r in results.items():
                if r is None:
                    continue
                s = r.get("score", 0.0)
                scores.append(s)
                if not r.get("passed", False):
                    failing.append({"table": table, "score": f"{s * 100:.0f}%"})
            if scores:
                result["pass_pct"] = f"{sum(scores) / len(scores) * 100:.0f}%"
            result["failing"] = failing
    return result


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def data_dashboard(request: Request, eng: ReadDep) -> HTMLResponse:
    stats = eng.pipeline_stats()
    sources = eng.config.data.sources or {}
    layers = eng.warehouse_layers()
    # Compute layer stats for accent card tier dots
    layer_stats: list[dict[str, Any]] = []
    for lyr in ("bronze", "silver", "gold"):
        tbl_count = 0
        with contextlib.suppress(Exception):
            tbl_count = len(eng.warehouse_tables(lyr))
        layer_stats.append({"layer": lyr, "count": tbl_count})
    table_count = sum(ls["count"] for ls in layer_stats)
    # Pipeline sparkbar data
    p_total = stats.get("total", 0)
    p_running = stats.get("running", 0)
    p_failed = stats.get("failed", 0)
    p_idle = max(0, p_total - p_running - p_failed)
    sparkbar_data: list[dict[str, str]] = []
    for _ in range(p_running):
        sparkbar_data.append({"status": "running", "height": "80"})
    for _ in range(p_failed):
        sparkbar_data.append({"status": "fail", "height": "70"})
    for _ in range(p_idle):
        sparkbar_data.append({"status": "ok", "height": "60"})
    sparkbar_data = sparkbar_data[:7]
    while len(sparkbar_data) < 7:
        sparkbar_data.insert(0, {"status": "empty", "height": "30"})
    # Recent runs & activity feed
    recent_runs = _build_dashboard_recent_runs(eng)
    activity_feed = _build_activity_feed(recent_runs)
    quality_summary = _build_quality_summary(eng)
    ctx = base_ctx(request) | {
        "stats": stats,
        "source_count": len(sources),
        "layers": layers,
        "layer_stats": layer_stats,
        "table_count": table_count,
        "sparkbar_data": sparkbar_data,
        "recent_runs": recent_runs,
        "activity_feed": activity_feed,
        "quality_summary": quality_summary,
        "active_tab": "data",
    }
    return render(request, "data/dashboard.html", ctx)


# ── Pipelines ────────────────────────────────────────────────────────────────


def _lineage_nid(s: str) -> str:
    return re.sub(r"\W+", "_", s).strip("_")[:40]


def _lineage_layer(p_name: str, p_cfg: Any) -> str:
    tgt = getattr(p_cfg, "target", None) or {}
    explicit: str | None = str(tgt["layer"]) if isinstance(tgt, dict) and tgt.get("layer") else None
    if explicit:
        return explicit
    if p_name.startswith("bronze_"):
        return "bronze"
    if p_name.startswith("gold_"):
        return "gold"
    return "silver"


def _lineage_nodes(by_layer: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    lane_x = {"source": 2, "bronze": 27, "silver": 52, "gold": 77}
    nodes: list[dict[str, Any]] = []
    node_ids: dict[str, str] = {}
    for layer, names in by_layer.items():
        n = len(names)
        for i, name in enumerate(sorted(names)):
            y = round((i + 1) * 88 / max(n + 1, 2)) + 5
            nid = _lineage_nid(name)
            node_ids[name] = nid
            nodes.append(
                {
                    "id": nid,
                    "name": name,
                    "layer": layer,
                    "x": lane_x[layer],
                    "y": y,
                    "fmt": "parquet",
                }
            )
    return nodes, node_ids


def _lineage_graph_from_config(eng: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build lineage nodes + edges from pipeline config (fallback when no recorded events)."""
    cfg = eng.config
    sources = list((cfg.data.sources or {}).keys())
    by_layer: dict[str, list[str]] = {"source": sources, "bronze": [], "silver": [], "gold": []}

    for p_name, p_cfg in (cfg.data.pipelines or {}).items():
        dest = p_cfg.destination or p_name
        lay = _lineage_layer(p_name, p_cfg)
        if dest not in by_layer[lay]:
            by_layer[lay].append(dest)

    nodes, node_ids = _lineage_nodes(by_layer)

    edges: list[dict[str, Any]] = []
    for p_cfg in (cfg.data.pipelines or {}).values():
        src, dest = p_cfg.source, p_cfg.destination or ""
        if src in node_ids and dest in node_ids:
            edges.append({"src": node_ids[src], "dst": node_ids[dest]})

    return nodes, edges


def _lineage_cls(name: str, layer: str = "") -> str:
    target = layer or name
    for lyr in ("bronze", "silver", "gold"):
        if lyr in target:
            return f":::{lyr}"
    return ":::source"


def _pipeline_status(last: Any) -> str:
    if last is None:
        return "never"
    return "success" if last.success else "failed"


def _pipeline_parquet_mtime(eng: Any, destination: str) -> str | None:
    """Return formatted mtime of the destination parquet if it exists in any layer."""
    dex_dir: Path = eng._dex_dir
    for layer in ("bronze", "silver", "gold"):
        p = dex_dir / "lakehouse" / layer / f"{destination}.parquet"
        if p.exists():
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
            return mtime.strftime("%b %d %H:%M")
    return None


def _pipeline_steps(cfg: Any) -> list[dict[str, str]]:
    """Extract transform steps from pipeline config into serialisable dicts."""
    raw = getattr(cfg, "steps", None) or getattr(cfg, "transforms", None) or []
    out: list[dict[str, str]] = []
    for s in raw:
        stype = str(getattr(s, "type", "transform"))
        cond = str(getattr(s, "condition", "") or "")
        sql = str(getattr(s, "sql", "") or "")
        key = getattr(s, "key", None)
        if cond:
            label = f"{stype}: {cond[:35]}…" if len(cond) > 35 else f"{stype}: {cond}"
        elif sql:
            first = sql.strip().splitlines()[0][:35]
            label = f"sql: {first}…" if len(sql.strip()) > 35 else f"sql: {first}"
        elif key:
            label = f"{stype}: {key}"
        else:
            label = stype
        out.append({"type": stype, "label": label})
    return out


def _next_run_iso(schedule: str, last_run_ts: Any) -> str:
    """Return ISO next-run timestamp for a cron schedule, or empty string."""
    if not schedule:
        return ""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from croniter import croniter as _cron  # type: ignore[import-untyped]

    try:
        if isinstance(last_run_ts, str):
            base: _dt = _dt.fromisoformat(last_run_ts)
        elif last_run_ts is not None:
            base = last_run_ts
        else:
            base = _dt.now(_UTC)
        if hasattr(base, "tzinfo") and base.tzinfo is None:
            base = base.replace(tzinfo=_UTC)
        now = _dt.now(_UTC)
        if base < now:
            base = now
        itr = _cron(schedule, base)
        nxt: _dt = itr.get_next(_dt)
        return nxt.replace(tzinfo=_UTC).isoformat()
    except Exception as exc:
        log.warning("next_run_iso failed", schedule=schedule, error=str(exc))
        return ""


def _build_pipeline_rows(eng: Any) -> list[dict[str, Any]]:
    rows = []
    sdb = get_studio_db(eng)
    for name, cfg in (eng.config.data.pipelines or {}).items():
        last = eng.pipeline_last_run(name)
        dest = str(cfg.destination or name)
        raw_schedule = getattr(cfg, "schedule", "") or ""

        if last is not None:
            last_run_ts: Any = last.timestamp
            status = _pipeline_status(last)
            duration_ms = f"{last.duration_ms:.0f}" if last.duration_ms else "—"
            rows_in = str(last.rows_input)
            rows_out = str(last.rows_output)
        else:
            # Engine DuckDB has no record — fall back to StudioDb which captures all runs
            db_runs = sdb.get_runs(name, limit=1) if sdb is not None else []
            if db_runs:
                db_r = db_runs[0]
                last_run_ts = db_r.get("finished_at") or db_r.get("started_at") or None
                raw_st = _norm_status(db_r.get("status", ""))
                status = raw_st if raw_st in ("success", "failed", "error", "running") else "never"
                dur_s = db_r.get("duration_s")
                duration_ms = f"{dur_s * 1000:.0f}" if dur_s is not None else "—"
            else:
                last_run_ts = None
                status = "never"
                duration_ms = "—"
            rows_in = "—"
            rows_out = "—"

        if is_pipeline_running(name):
            status = "running"

        last_run = fmt_ts(last_run_ts)
        if last_run == "—":
            last_run = _pipeline_parquet_mtime(eng, dest) or "—"

        rows.append(
            {
                "name": name,
                "schedule": fmt_cron(raw_schedule) if raw_schedule else "—",
                "next_run_at": _next_run_iso(raw_schedule, last_run_ts),
                "status": status,
                "last_run": last_run,
                "duration_ms": duration_ms,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "source": str(cfg.source or ""),
                "destination": dest,
                "steps": _pipeline_steps(cfg),
            }
        )
    return rows


def _serialize_run(r: Any) -> dict[str, Any]:
    """Serialise a single pipeline run record to a JSON-safe dict."""
    return {
        "run_id": r.run_id,
        "pipeline_name": r.pipeline_name,
        "timestamp": fmt_ts(r.timestamp),
        "success": r.success,
        "duration_ms": round(r.duration_ms, 0) if r.duration_ms else None,
        "rows_output": r.rows_output,
        "error": r.error or "",
    }


def _norm_status(status: str) -> str:
    """Normalise scheduler's 'failure' → 'failed' for consistent display."""
    return "failed" if status == "failure" else status


def _serialize_db_run(r: dict[str, Any]) -> dict[str, Any]:
    """Serialise a StudioDb pipeline_runs row to the same shape as _serialize_run."""
    dur_s = r.get("duration_s")
    status = _norm_status(r.get("status", ""))
    ts = r.get("finished_at") or r.get("started_at") or ""
    return {
        "run_id": r.get("id", 0),
        "pipeline_name": r.get("pipeline", ""),
        "timestamp": fmt_ts(ts),
        "started": fmt_ts_iso(ts),
        "success": status == "success",
        "duration_ms": round(dur_s * 1000, 0) if dur_s is not None else None,
        "duration": _fmt_dur_s(dur_s),
        "rows_output": None,
        "error": r.get("error") or "",
        "trigger": r.get("triggered_by") or "scheduler",
        "status": status,
    }


def _sparkbar_for_pipeline(eng: Any, name: str) -> list[dict[str, str]]:
    bars: list[dict[str, str]] = []
    sdb = get_studio_db(eng)
    if sdb is not None:
        with contextlib.suppress(Exception):
            for r in sdb.get_runs(name, limit=7):
                st = r.get("status", "")
                bars.append({"status": "ok" if st == "success" else "fail", "height": "70"})
    if not bars:
        with contextlib.suppress(Exception):
            for r in reversed(eng.store.get_pipeline_runs(name)[:7]):
                bars.append({"status": "ok" if r.success else "fail", "height": "70"})
    while len(bars) < 7:
        bars.insert(0, {"status": "empty", "height": "30"})
    return bars[-7:]


@router.get("/pipelines/status")
def pipelines_status(request: Request, eng: JsonReadDep) -> Any:
    """Lightweight JSON — status/last_run/next_run_at for live polling."""
    return [
        {
            "name": r["name"],
            "status": r["status"],
            "last_run": r["last_run"],
            "next_run_at": r["next_run_at"],
        }
        for r in _build_pipeline_rows(eng)
    ]


@router.get("/pipelines", response_class=HTMLResponse)
def pipelines(request: Request, eng: ReadDep) -> HTMLResponse:
    rows = _build_pipeline_rows(eng)
    pipeline_data = {
        r["name"]: {"source": r["source"], "destination": r["destination"], "steps": r["steps"]}
        for r in rows
    }
    sparkbar_by_pipeline = {r["name"]: _sparkbar_for_pipeline(eng, r["name"]) for r in rows}
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "source_types": _SOURCE_TYPES,
        "pipeline_data_json": _json.dumps(pipeline_data),
        "sparkbar_by_pipeline": sparkbar_by_pipeline,
    }
    return render(request, "data/pipelines.html", ctx)


@router.get("/pipelines/runs", response_class=HTMLResponse)
def pipeline_runs_page(request: Request, eng: ReadDep) -> HTMLResponse:
    """HTML — paginated run history for all pipelines."""
    sdb = get_studio_db(eng)
    db_runs = sdb.get_runs(None, limit=200) if sdb is not None else []
    runs = [_serialize_db_run(r) for r in db_runs]
    if not runs:
        for r in reversed(eng.store.get_pipeline_runs()[-200:]):
            runs.append(_serialize_run(r))
    ctx = base_ctx(request) | {
        "runs": runs,
        "total_count": len(runs),
        "pipeline_name": None,
    }
    return render(request, "data/pipeline_runs.html", ctx)


@router.get("/pipelines/{name}/runs/detail", response_class=HTMLResponse)
def pipeline_runs_detail_page(request: Request, eng: ReadDep, name: str) -> HTMLResponse:
    """HTML — run history for a single pipeline."""
    sdb = get_studio_db(eng)
    db_runs = sdb.get_runs(name, limit=100) if sdb is not None else []
    runs = [_serialize_db_run(r) for r in db_runs]
    if not runs:
        runs = [_serialize_run(r) for r in eng.store.get_pipeline_runs(name)[:100]]
    ctx = base_ctx(request) | {
        "runs": runs,
        "total_count": len(runs),
        "pipeline_name": name,
    }
    return render(request, "data/pipeline_runs.html", ctx)


@router.get("/pipelines/runs/all")
def pipeline_runs_all(request: Request, eng: JsonReadDep) -> Any:
    """JSON — last 50 runs across all pipelines."""
    from fastapi.responses import JSONResponse

    sdb = get_studio_db(eng)
    if sdb is not None:
        db_runs = sdb.get_runs(None, limit=50)
        if db_runs:
            return JSONResponse([_serialize_db_run(r) for r in db_runs])
    runs = eng.store.get_pipeline_runs(None)[:50]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.get("/pipelines/{name}/runs")
def pipeline_runs_for(request: Request, eng: JsonReadDep, name: str) -> Any:
    """JSON — last 20 runs for a single pipeline."""
    from fastapi.responses import JSONResponse

    sdb = get_studio_db(eng)
    if sdb is not None:
        db_runs = sdb.get_runs(name, limit=20)
        if db_runs:
            return JSONResponse([_serialize_db_run(r) for r in db_runs])
    runs = eng.store.get_pipeline_runs(name)[:20]
    return JSONResponse([_serialize_run(r) for r in runs])


@router.post("/pipelines/run/{name}")
def run_pipeline(request: Request, _: WriteDep, name: str) -> RedirectResponse:
    status = run_pipeline_bg(name)
    if status == "started":
        flash(request, f"Pipeline '{name}' started — refresh in a moment for results.")
    elif status == "running":
        flash(request, f"Pipeline '{name}' is already running.", "warning")
    elif status == "low_memory":
        flash(request, "Not enough memory to run a pipeline safely. Free up RAM first.", "error")
    else:
        flash(request, "System busy — too many pipelines queued. Try again shortly.", "warning")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/run-all")
def run_all_pipelines(request: Request, _: WriteDep) -> RedirectResponse:
    status = run_all_pipelines_bg()
    if status == "started":
        flash(request, "All pipelines queued — running in dependency order.")
    elif status == "running":
        flash(request, "A full run is already in progress.", "warning")
    elif status == "low_memory":
        flash(request, "Not enough memory to run pipelines safely.", "error")
    else:
        flash(request, "System busy — try again shortly.", "warning")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/add")
def add_pipeline(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    source: Annotated[str, Form()] = "",
    schedule: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        eng.add_pipeline(name.strip(), source.strip(), schedule.strip(), destination.strip())
        flash(request, f"Pipeline '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/delete/{name}")
def delete_pipeline(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_pipeline(name)
        flash(request, f"Pipeline '{name}' deleted.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/pipelines", status_code=303)


@router.post("/pipelines/{name}/schedule")
def update_schedule(
    request: Request,
    eng: WriteDep,
    name: str,
    schedule: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        eng.update_pipeline_schedule(name, schedule.strip() or None)
        flash(request, f"Schedule updated for '{name}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/pipelines/{name}", status_code=303)


@router.get("/pipelines/{name}", response_class=HTMLResponse)
def pipeline_detail(request: Request, eng: ReadDep, name: str) -> HTMLResponse:
    cfg = (eng.config.data.pipelines or {}).get(name)
    if cfg is None:
        return RedirectResponse("/data/pipelines", status_code=303)  # type: ignore[return-value]
    sdb = get_studio_db(eng)
    db_runs = sdb.get_runs(name, limit=20) if sdb is not None else []
    if db_runs:
        history = [
            {
                "timestamp": fmt_ts(r.get("finished_at") or r.get("started_at")),
                "success": r.get("status") == "success",
                "rows_input": "—",
                "rows_output": "—",
                "duration_ms": _fmt_dur_s(r.get("duration_s")),
                "error": r.get("error") or "",
            }
            for r in db_runs
        ]
    else:
        runs = eng.store.get_pipeline_runs(name)
        history = [
            {
                "timestamp": fmt_ts(r.timestamp),
                "success": r.success,
                "rows_input": r.rows_input,
                "rows_output": r.rows_output,
                "duration_ms": f"{r.duration_ms:.0f}" if r.duration_ms else "—",
                "error": r.error or "",
            }
            for r in runs[:20]
        ]
    steps = []
    if hasattr(cfg, "steps") and cfg.steps:
        for s in cfg.steps:
            steps.append(
                {
                    "type": getattr(s, "type", ""),
                    "name": getattr(s, "name", ""),
                    "sql": getattr(s, "sql", ""),
                }
            )
    # Build source_info / dest_info for the template
    src_cfg = (eng.config.data.sources or {}).get(cfg.source or "")
    src_query = getattr(src_cfg, "query", None) if src_cfg else None
    source_info = SimpleNamespace(
        name=cfg.source or "—",
        schedule=fmt_cron(cfg.schedule or ""),
        endpoint=getattr(src_cfg, "url", None) if src_cfg else "—",
        auth="—",
        fetch_mode="incremental" if src_query else "full",
        watermark_col="",
        last_watermark="—",
    )
    dst = getattr(cfg, "destination", None) or name
    dest_info = SimpleNamespace(
        table=dst,
        layer="bronze",
        scd_type=1,
        pk_col="id",
        current_flag="",
        effective_from="",
        effective_to="",
    )
    # Compute stats summary from history
    total_runs = len(history)
    success_count = sum(1 for h in history if h["success"])
    stats = SimpleNamespace(
        rows_total=str(total_runs) if total_runs else "—",
        success_rate=f"{success_count / total_runs * 100:.0f}%" if total_runs else "—",
        next_run=_next_run_iso(cfg.schedule or "", history[0]["timestamp"] if history else None),
    )
    ctx = base_ctx(request) | {
        "pipeline_name": name,
        "schedule": fmt_cron(cfg.schedule or ""),
        "source": cfg.source or "—",
        "destination": getattr(cfg, "destination", None) or "—",
        "history": history,
        "steps": steps,
        "source_info": source_info,
        "dest_info": dest_info,
        "stats": stats,
    }
    return render(request, "data/pipeline_detail.html", ctx)


# ── Sources ──────────────────────────────────────────────────────────────────


def _get_watermark_store(eng: Any) -> Any | None:
    """Return a WatermarkStore for the current project, or None if unavailable."""
    try:
        from dex_studio.scheduler import _get_or_create_studio_db  # type: ignore[attr-defined]
        from dex_studio.watermark import WatermarkStore
    except ImportError:
        return None
    db = None
    with contextlib.suppress(Exception):
        db = _get_or_create_studio_db(eng)
    if db is None:
        return None
    return WatermarkStore(db)


_SENSITIVE_KEYS = frozenset({"secret", "token", "password", "key", "pass", "auth", "cred"})


def _mask_config_value(k: str, v: Any) -> str:
    k_lower = k.lower()
    if any(s in k_lower for s in _SENSITIVE_KEYS):
        return "••••••••"
    return str(v)


def _build_source_rows(eng: Any) -> list[dict[str, str]]:
    store = _get_watermark_store(eng)
    wm_rows = store.all_watermarks() if store else []
    last_synced_map = {w["source"]: fmt_ts_iso(w.get("updated_at") or "") for w in wm_rows}
    rows = []
    for name, cfg in (eng.config.data.sources or {}).items():
        connector_type = str(getattr(cfg, "type", "http"))
        rows.append(
            {
                "name": name,
                "type": str(getattr(cfg, "type", "—")),
                "status": "active",
                "connector_type": connector_type,
                "last_synced": last_synced_map.get(name, "—"),
            }
        )
    return rows


def _build_source_data(eng: Any) -> dict[str, Any]:
    """Build JSON-serialisable dict keyed by source name for the master-detail JS panel."""
    result: dict[str, Any] = {}
    for name, cfg in (eng.config.data.sources or {}).items():
        connector = str(getattr(cfg, "type", "http"))
        row_count: Any = "—"
        schema: list[dict[str, str]] = []
        sample_rows: list[dict[str, Any]] = []
        config_display: list[dict[str, str]] = []
        last_fetched = "—"

        with contextlib.suppress(Exception):
            stats = eng.source_stats(name) or {}
            row_count = stats.get("row_count", "—")
        with contextlib.suppress(Exception):
            schema_raw = eng.source_schema(name) or []
            schema = [
                {
                    "name": str(col.get("column_name", col.get("name", ""))),
                    "type": str(col.get("data_type", col.get("type", ""))),
                }
                for col in schema_raw
            ]
        with contextlib.suppress(Exception):
            raw_rows = eng.source_sample(name, limit=5) or []
            sample_rows = [dict(r) for r in raw_rows]
        # Config display — mask sensitive values
        cfg_dict = vars(cfg) if hasattr(cfg, "__dict__") else {}
        if isinstance(cfg_dict, dict):
            config_display = [
                {"key": k, "value": _mask_config_value(k, v)}
                for k, v in cfg_dict.items()
                if not k.startswith("_") and v is not None
            ]

        store = _get_watermark_store(eng)
        if store:
            with contextlib.suppress(Exception):
                for w in store.all_watermarks():
                    if w.get("source") == name:
                        last_fetched = fmt_ts_iso(w.get("updated_at") or "")
                        break

        result[name] = {
            "connector": connector,
            "row_count": row_count,
            "schema": schema,
            "sample_rows": sample_rows,
            "sample_cols": [c["name"] for c in schema[:8]],
            "config_display": config_display,
            "last_fetched": last_fetched,
        }
    return result


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request, eng: ReadDep) -> HTMLResponse:
    rows = _build_source_rows(eng)
    source_data = _build_source_data(eng)
    ctx = base_ctx(request) | {
        "sources": rows,
        "source_types": _SOURCE_TYPES,
        "source_data_json": _json.dumps(source_data),
    }
    return render(request, "data/sources.html", ctx)


@router.get("/sources/{name}", response_class=HTMLResponse)
def source_detail(request: Request, eng: ReadDep, name: str) -> HTMLResponse:
    stats = eng.source_stats(name) or {}
    schema = eng.source_schema(name) or []
    sample_rows = eng.source_sample(name, limit=10) or []
    sample_cols = list(sample_rows[0].keys()) if sample_rows else []
    ctx = base_ctx(request) | {
        "source_name": name,
        "stats": stats,
        "schema": schema,
        "sample_rows": sample_rows,
        "sample_cols": sample_cols,
    }
    return render(request, "data/source_detail.html", ctx)


def _source_connection(
    type_: str,
    spark_master: str,
    spark_format: str,
    dbt_project_dir: str,
    dbt_model: str,
    dbt_target: str,
) -> dict[str, Any] | None:
    if type_ == "spark":
        conn = {k: v for k, v in {"master": spark_master, "format": spark_format}.items() if v}
        return conn or None
    if type_ == "dbt":
        conn = {
            k: v
            for k, v in {
                "project_dir": dbt_project_dir,
                "model": dbt_model,
                "target": dbt_target,
            }.items()
            if v
        }
        return conn or None
    return None


@router.post("/sources/add")
def add_source(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    type_: Annotated[str, Form(alias="type")],
    path: Annotated[str, Form()] = "",
    spark_master: Annotated[str, Form()] = "",
    spark_format: Annotated[str, Form()] = "",
    dbt_project_dir: Annotated[str, Form()] = "",
    dbt_model: Annotated[str, Form()] = "",
    dbt_target: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        t = type_.strip()
        connection = _source_connection(
            t,
            spark_master.strip(),
            spark_format.strip(),
            dbt_project_dir.strip(),
            dbt_model.strip(),
            dbt_target.strip(),
        )
        eng.add_source(name.strip(), t, path.strip(), connection=connection)
        flash(request, f"Source '{name}' added.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


@router.post("/sources/delete/{name}")
def delete_source(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    try:
        eng.delete_source(name)
        flash(request, f"Source '{name}' removed.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/sources", status_code=303)


# ── SQL Console ───────────────────────────────────────────────────────────────


_DEFAULT_SQL = (
    "SELECT table_name, table_schema, table_type\n"
    "FROM information_schema.tables\n"
    "ORDER BY table_schema, table_name\n"
    "LIMIT 50;"
)

# Matches the start of any statement that writes, loads external data, or
# escapes the lakehouse sandbox. Checked before execution.
_UNSAFE_SQL = re.compile(
    r"""
    ^\s*
    (
        INSERT | UPDATE | DELETE | MERGE |       # DML
        CREATE | DROP   | ALTER  | TRUNCATE |    # DDL
        ATTACH | DETACH |                      # multi-file access
        COPY   | EXPORT | IMPORT |             # file I/O
        LOAD   | INSTALL |                     # extension loading
        PRAGMA                                   # internals
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# read_* functions can reference arbitrary paths outside the lakehouse
_UNSAFE_FUNCTIONS = re.compile(
    r"\bread_(csv|parquet|json|ndjson|text|xml|avro|orc|feather|arrow)\s*\(",
    re.IGNORECASE,
)

# DuckDB allows `FROM '/path/to/file'` as a shorthand for read_*() — block it.
_UNSAFE_LITERAL_FROM = re.compile(r"""\bFROM\s+['"]""", re.IGNORECASE)


def _validate_sql(query: str) -> str | None:
    """Return an error string if query is not allowed, else None."""
    stripped = query.strip()
    if not stripped:
        return "Query is empty."
    if _UNSAFE_SQL.match(stripped):
        return (
            "Only SELECT queries are allowed in the SQL console. "
            "DML, DDL, ATTACH, COPY, LOAD and INSTALL are disabled."
        )
    if _UNSAFE_FUNCTIONS.search(stripped):
        return (
            "Direct read_*() calls are disabled. "
            "Query the pre-registered table views instead (listed in the sidebar)."
        )
    if _UNSAFE_LITERAL_FROM.search(stripped):
        return (
            "Literal file paths in FROM clauses are disabled. "
            "Query the pre-registered table views instead."
        )
    return None


@router.get("/sql", response_class=HTMLResponse)
def sql_console(request: Request, eng: ReadDep) -> HTMLResponse:
    catalog_entries: list[dict[str, Any]] = []
    for layer in ("bronze", "silver", "gold"):
        for tbl in eng.warehouse_tables(layer):
            schema = eng.warehouse_table_schema(tbl["name"], layer) or []
            catalog_entries.append(
                {"name": tbl["name"], "layer": layer, "column_count": len(schema)}
            )
    ctx = base_ctx(request) | {
        "sql_results": [],
        "sql_columns": [],
        "exec_ms": None,
        "catalog_entries": catalog_entries,
        "default_sql": _DEFAULT_SQL,
    }
    return render(request, "data/sql.html", ctx)


def _run_sql(
    lakehouse: Path, query: str
) -> tuple[list[str], list[dict[str, Any]], float | None, str]:
    """Execute *query* against lakehouse views. Returns (columns, rows, exec_ms, error)."""
    columns: list[str] = []
    results: list[dict[str, Any]] = []
    exec_ms: float | None = None
    try:
        t0 = time.monotonic()
        with duckdb.connect(":memory:") as conn:
            for layer in ("bronze", "silver", "gold"):
                layer_path = lakehouse / layer
                if layer_path.exists():
                    for pf in sorted(layer_path.glob("*.parquet")):
                        safe = str(pf.resolve())
                        with contextlib.suppress(Exception):
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {pf.stem} AS"
                                f" SELECT * FROM read_parquet('{safe}')"
                            )
                            conn.execute(
                                f"CREATE VIEW IF NOT EXISTS {layer}_{pf.stem} AS"
                                f" SELECT * FROM read_parquet('{safe}')"
                            )
            cursor = conn.execute(query)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                results = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        exec_ms = (time.monotonic() - t0) * 1000
    except Exception as exc:
        return [], [], None, str(exc)
    return columns, results, exec_ms, ""


@router.post("/sql/execute", response_class=HTMLResponse)
def execute_sql(
    request: Request,
    eng: WriteDep,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    error = _validate_sql(query) or ""
    columns: list[str] = []
    results: list[dict[str, Any]] = []
    exec_ms: float | None = None

    if not error:
        lakehouse = eng.project_dir / ".dex" / "lakehouse"
        columns, results, exec_ms, error = _run_sql(lakehouse, query)

    # Build catalog sidebar entries (needed when rendering the full sql.html page)
    catalog_entries: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        for _layer in ("bronze", "silver", "gold"):
            for _tbl in eng.warehouse_tables(_layer):
                _schema = eng.warehouse_table_schema(_tbl["name"], _layer) or []
                catalog_entries.append(
                    {"name": _tbl["name"], "layer": _layer, "column_count": len(_schema)}
                )

    ctx = base_ctx(request) | {
        "query": query,
        "sql_results": results,
        "sql_columns": columns,
        "error": error,
        "exec_ms": exec_ms,
        "catalog_entries": catalog_entries,
        "default_sql": query,
    }
    if request.headers.get("HX-Request"):
        return render(request, "data/sql_results.html", ctx)
    return render(request, "data/sql.html", ctx)


# ── Lakehouse (all layers: Bronze · Silver · Gold) ────────────────────────────


@router.get("/lakehouse", response_class=HTMLResponse)
def lakehouse(request: Request, eng: ReadDep, layer: str = "") -> HTMLResponse:
    layers = eng.warehouse_layers()
    if not layer:
        nonempty = (lyr["name"] for lyr in layers if lyr.get("table_count", 0) > 0)
        layer = next(nonempty, "") or "bronze"
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {
        "layers": layers,
        "active_layer": layer,
        "tables": tables,
    }
    return render(request, "data/lakehouse.html", ctx)


@router.get("/lakehouse/tables", response_class=HTMLResponse)
def lakehouse_tables_partial(request: Request, eng: ReadDep, layer: str = "bronze") -> HTMLResponse:
    tables = eng.warehouse_tables(layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Warehouse (Gold layer — BI-ready structured data) ─────────────────────────


def _enrich_tables(eng: Any, tables: list[dict[str, Any]], layer: str) -> list[dict[str, Any]]:
    enriched = []
    for tbl in tables:
        name = tbl.get("name", "")
        try:
            schema = eng.warehouse_table_schema(name, layer) or []
            col_count = len(schema)
        except Exception:  # noqa: BLE001
            col_count = 0
        enriched.append({**tbl, "column_count": col_count})
    return enriched


@router.get("/warehouse", response_class=HTMLResponse)
def warehouse(request: Request, eng: ReadDep) -> HTMLResponse:
    tables = _enrich_tables(eng, eng.warehouse_tables("gold"), "gold")
    ctx = base_ctx(request) | {
        "tables": tables,
        "active_layer": "gold",
    }
    return render(request, "data/warehouse.html", ctx)


@router.get("/warehouse/tables", response_class=HTMLResponse)
def warehouse_tables_partial(request: Request, eng: ReadDep, layer: str = "bronze") -> HTMLResponse:
    tables = _enrich_tables(eng, eng.warehouse_tables(layer), layer)
    ctx = base_ctx(request) | {"tables": tables, "active_layer": layer}
    return render(request, "data/warehouse_tables.html", ctx)


# ── Lineage ───────────────────────────────────────────────────────────────────


_MERMAID_STYLE = [
    "  classDef source fill:#e8e8e8,stroke:#aaa,color:#333",
    "  classDef bronze fill:#fef3c7,stroke:#d97706,color:#92400e",
    "  classDef silver fill:#dbeafe,stroke:#3b82f6,color:#1e40af",
    "  classDef gold fill:#fef9c3,stroke:#ca8a04,color:#713f12",
]


def _node_id(name: str) -> str:
    # For file paths, use "{layer}_{stem}" to keep IDs short and stable
    if os.sep in name or (name.startswith("/") or name.startswith(".")):
        stem = os.path.splitext(os.path.basename(name))[0]
        for lyr in ("bronze", "silver", "gold"):
            if lyr in name:
                return re.sub(r"\W", "_", f"{lyr}_{stem}")[:64]
        return re.sub(r"\W", "_", stem)[:64]
    return re.sub(r"\W", "_", name)[:64]


def _node_label(name: str) -> str:
    label = os.path.splitext(os.path.basename(name))[0] or name
    return label[:40]


def _node_click_url(node_name: str, is_source: bool) -> str:
    if is_source:
        return f"/data/sources/{node_name}" if node_name and "/" not in node_name else ""
    for layer in ("bronze", "silver", "gold"):
        if layer in node_name:
            return f"/data/warehouse?layer={layer}"
    return ""


def _node_tooltip(name: str, is_source: bool, pipe_names: list[str]) -> str:
    kind = "Source" if is_source else "Table"
    pipes = ", ".join(pipe_names) if pipe_names else "—"
    return f"{kind}: {_node_label(name)} | Pipelines: {pipes}"


def _register_node(
    name: str,
    is_source: bool,
    node_lines: list[str],
    click_lines: list[str],
    seen: set[str],
    pipe_names: list[str],
    layer: str = "",
) -> None:
    nid = _node_id(name)
    if nid in seen:
        return
    node_lines.append(f'  {nid}["{_node_label(name)}"]{_lineage_cls(name, layer)}')
    seen.add(nid)
    url = _node_click_url(name, is_source)
    if url:
        tip = _node_tooltip(name, is_source, pipe_names).replace('"', "'")
        click_lines.append(f'  click {nid} "{url}" "{tip}"')


def _build_mermaid(events: list[dict[str, Any]]) -> str:
    node_lines: list[str] = []
    click_lines: list[str] = []
    edge_lines: list[str] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    # Gather per-node pipeline names for tooltips
    node_pipes: dict[str, list[str]] = {}
    for e in events:
        for node in (e["source"], e["target"]):
            node_pipes.setdefault(node, [])
            pn = e["pipeline_name"]
            if pn and pn not in node_pipes[node]:
                node_pipes[node].append(pn)
    for e in events:
        src_name, tgt_name, pipe_name = e["source"], e["target"], e["pipeline_name"]
        layer = e.get("layer", "")
        _register_node(
            src_name, True, node_lines, click_lines, seen_nodes, node_pipes.get(src_name, [])
        )
        _register_node(
            tgt_name,
            False,
            node_lines,
            click_lines,
            seen_nodes,
            node_pipes.get(tgt_name, []),
            layer,
        )
        edge_key = (_node_id(src_name), _node_id(tgt_name), _node_id(pipe_name))
        if edge_key not in seen_edges:
            edge_lines.append(f"  {edge_key[0]} -->|{_node_label(pipe_name)}| {edge_key[1]}")
            seen_edges.add(edge_key)
    return "\n".join(["flowchart LR", *node_lines, *edge_lines, *click_lines, *_MERMAID_STYLE])


def _get_lineage_events(eng: Any, pipeline: str = "") -> list[dict[str, Any]]:
    events = [
        {
            "id": getattr(e, "event_id", ""),
            "source": getattr(e, "source", ""),
            "target": getattr(e, "destination", ""),
            "layer": getattr(e, "layer", ""),
            "pipeline_name": getattr(e, "pipeline_name", ""),
            "timestamp": fmt_ts(getattr(e, "timestamp", "")),
        }
        for e in (eng.lineage.all_events if eng.lineage else [])
    ]
    if pipeline:
        events = [e for e in events if e["pipeline_name"] == pipeline]
    return events


@router.get("/lineage/graph-partial", response_class=HTMLResponse)
def lineage_graph_partial(request: Request, eng: ReadDep, pipeline: str = "") -> HTMLResponse:
    events = _get_lineage_events(eng, pipeline)
    diagram = _build_mermaid(events) if events else ""
    if diagram:
        html = f'<pre class="mermaid" style="background:transparent;font-size:13px">{diagram}</pre>'
    else:
        html = '<p style="font-size:13px;color:var(--gray-9)">No graph data available.</p>'
    return HTMLResponse(html)


@router.get("/lineage", response_class=HTMLResponse)
def lineage(
    request: Request, eng: ReadDep, pipeline: str = "", view: str = "table"
) -> HTMLResponse:
    all_events = _get_lineage_events(eng, pipeline)
    pipeline_names = sorted({e["pipeline_name"] for e in all_events if e["pipeline_name"]})
    lin_nodes, lin_edges = _lineage_graph_from_config(eng)
    ctx = base_ctx(request) | {
        "events": all_events,
        "pipeline_names": pipeline_names,
        "filter_pipeline": pipeline,
        "view": view,
        "lineage_nodes": lin_nodes,
        "lineage_edges": lin_edges,
        "mermaid_diagram": _build_mermaid(all_events) if all_events else "",
    }
    return render(request, "data/lineage.html", ctx)


# ── Data Quality ──────────────────────────────────────────────────────────────


def _parse_quality_run(
    run: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Return (checks, overall_pct) from a single quality run dict."""
    checks: list[dict[str, Any]] = []
    scores: list[float] = []
    for table, r in run.get("results", {}).items():
        if r is None:
            continue
        s = float(r.get("score", 0.0))
        scores.append(s)
        checks.append(
            {
                "table": table,
                "score": f"{s * 100:.0f}%",
                "completeness": f"{r.get('completeness', 0) * 100:.0f}%",
                "uniqueness": f"{r.get('uniqueness', 0) * 100:.0f}%",
                "passed": bool(r.get("passed", False)),
            }
        )
    overall = f"{sum(scores) / len(scores) * 100:.0f}%" if scores else "—"
    return checks, overall


def _pipeline_quality_summary(eng: Any) -> list[dict[str, Any]]:
    """Build per-pipeline quality check counts from config."""
    summary: list[dict[str, Any]] = []
    pipelines_cfg = getattr(eng.config.data, "pipelines", None) or {}
    for pipe_name, pipe_cfg in pipelines_cfg.items():
        q = getattr(pipe_cfg, "quality", None)
        if q is None:
            continue
        check_count = sum(
            1
            for attr in ("completeness", "row_count_min", "uniqueness", "custom_sql")
            if getattr(q, attr, None) is not None
        )
        if check_count == 0:
            continue
        summary.append(
            {
                "name": pipe_name,
                "check_count": check_count,
                "pass_count": check_count,
                "fail_count": 0,
                "last_checked": "—",
            }
        )
    return summary


@router.get("/quality", response_class=HTMLResponse)
def quality(request: Request, eng: ReadDep) -> HTMLResponse:
    history: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        history = eng.quality_history()
    runs: list[dict[str, Any]] = history.get("runs", [])

    checks: list[dict[str, Any]] = []
    overall_pass_pct = "—"
    if runs:
        checks, overall_pass_pct = _parse_quality_run(runs[0])

    quality_events: list[dict[str, Any]] = []
    if runs and checks:
        run_ts = fmt_ts_iso(runs[0].get("timestamp", "") or "")
        quality_events = [
            {
                "table": c["table"],
                "check_type": "overall",
                "passed": c["passed"],
                "score": c["score"],
                "timestamp": run_ts,
            }
            for c in checks
        ]

    ctx = base_ctx(request) | {
        "score_pct": overall_pass_pct,
        "overall_pass_pct": overall_pass_pct,
        "checks": checks,
        "run_count": len(runs),
        "quality_by_pipeline": _pipeline_quality_summary(eng),
        "quality_events": quality_events,
    }
    return render(request, "data/quality.html", ctx)


@router.post("/quality/run")
def run_quality(request: Request, eng: WriteDep) -> RedirectResponse:
    try:
        eng.quality_check_all_tables()
        flash(request, "Quality checks complete.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/quality", status_code=303)


@router.post("/quality/tests/add")
def add_quality_test(
    request: Request,
    eng: WriteDep,
    table: Annotated[str, Form()],
    test_type: Annotated[str, Form()],
    column: Annotated[str, Form()] = "",
    threshold: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        tests_path = eng.project_dir / ".dex" / "quality_tests.json"
        existing: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            existing = _json.loads(tests_path.read_text())
        existing.append(
            {
                "table": table,
                "test_type": test_type,
                "column": column,
                "threshold": threshold,
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )
        tests_path.parent.mkdir(parents=True, exist_ok=True)
        tests_path.write_text(_json.dumps(existing, indent=2))
        flash(request, f"Test '{test_type}' added for table '{table}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/quality", status_code=303)


@router.post("/catalog/register")
def catalog_register(
    request: Request,
    eng: WriteDep,
    table_name: Annotated[str, Form()],
    file_path: Annotated[str, Form()],
    layer: Annotated[str, Form()] = "bronze",
) -> RedirectResponse:
    try:
        import shutil

        project_root = eng.project_dir.resolve()
        # Build a server-side index of project files so src is never derived
        # from user input — eliminates the path traversal taint flow entirely.
        _valid_exts = frozenset({".parquet", ".csv", ".json", ".ndjson"})
        project_files: dict[str, Path] = {
            str(f.relative_to(project_root)): f
            for f in project_root.rglob("*")
            if f.is_file() and f.suffix.lower() in _valid_exts
        }
        # Normalise user input to a relative key for the lookup
        raw = file_path.strip()
        project_str = str(project_root)
        if raw.startswith(project_str):
            raw = raw[len(project_str) :].lstrip("/\\")
        raw = raw.lstrip("/\\")
        # src comes from the filesystem index, never from user input
        src = project_files.get(raw)
        if src is None:
            flash(request, "File not found in project directory.", "error")
            return RedirectResponse("/data/catalog", status_code=303)
        dest_dir = eng.project_dir / ".dex" / "lakehouse" / layer
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-z0-9_]", "_", table_name.strip().lower())
        dest = dest_dir / f"{safe_name}.parquet"
        if src.suffix.lower() == ".csv":
            duckdb.execute(
                "COPY (SELECT * FROM read_csv_auto(?)) TO ? (FORMAT PARQUET)",
                [str(src), str(dest)],
            )
        else:
            shutil.copy2(src, dest)
        flash(request, f"Table '{safe_name}' registered in {layer} layer.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/data/catalog", status_code=303)


# ── Catalog (alias for sources) ───────────────────────────────────────────────


@router.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request, eng: ReadDep) -> HTMLResponse:
    entries: list[dict[str, Any]] = []
    layer_colors = {"bronze": "orange", "silver": "indigo", "gold": "amber"}
    for layer in ("bronze", "silver", "gold"):
        for table in eng.warehouse_tables(layer):
            schema = eng.warehouse_table_schema(table["name"], layer) or []
            entries.append(
                {
                    "name": table["name"],
                    "layer": layer,
                    "layer_color": layer_colors[layer],
                    "row_count": table.get("row_count", "—"),
                    "column_count": len(schema),
                    "size": table.get("size", "—"),
                    "columns": schema,
                    "format": "parquet",
                }
            )
    ctx = base_ctx(request) | {"entries": entries, "active_tab": "data"}
    return render(request, "data/catalog.html", ctx)


@router.get("/catalog/{table_name}", response_class=HTMLResponse)
def catalog_detail(request: Request, eng: ReadDep, table_name: str) -> HTMLResponse:
    # Find the layer this table lives in
    found_layer: str | None = None
    found_path: str | None = None
    for layer in ("bronze", "silver", "gold"):
        for tbl in eng.warehouse_tables(layer):
            if tbl["name"] == table_name:
                found_layer = layer
                found_path = tbl.get("path")
                break
        if found_layer:
            break
    if not found_layer or not found_path:
        from fastapi.responses import Response

        return Response(status_code=404)  # type: ignore[return-value]
    schema = eng.warehouse_table_schema(table_name, found_layer) or []
    stats = eng.warehouse_table_stats(table_name, found_layer)
    lineage = eng.warehouse_table_lineage(table_name, found_layer)
    # Preview rows (first 8)
    preview_cols: list[str] = []
    preview_rows: list[list[Any]] = []
    with contextlib.suppress(Exception), duckdb.connect() as conn:
        rel = conn.execute(f"SELECT * FROM read_parquet('{found_path}') LIMIT 8")
        preview_cols = [d[0] for d in (rel.description or [])]
        preview_rows = [list(r) for r in rel.fetchall()]
    size_bytes = stats.get("size_bytes", 0)
    size_fmt = (
        f"{size_bytes / 1_048_576:.1f} MB"
        if size_bytes >= 1_048_576
        else f"{size_bytes / 1024:.1f} KB"
    )
    ctx = base_ctx(request) | {
        "active_tab": "data",
        "table_name": table_name,
        "layer": found_layer,
        "schema": schema,
        "row_count": stats.get("row_count", "—"),
        "column_count": stats.get("column_count", len(schema)),
        "size": size_fmt,
        "upstream": lineage.get("upstream", []),
        "downstream": lineage.get("downstream", []),
        "preview_cols": preview_cols,
        "preview_rows": preview_rows,
    }
    return render(request, "data/catalog_detail.html", ctx)


# ── Transforms ───────────────────────────────────────────────────────────────


@router.get("/transforms", response_class=HTMLResponse)
def transforms(request: Request, eng: ReadDep, pipeline: str = "") -> HTMLResponse:
    rows = _build_pipeline_rows(eng)
    if not pipeline and rows:
        pipeline = rows[0]["name"]
    cfg = (eng.config.data.pipelines or {}).get(pipeline) if pipeline else None
    steps: list[dict[str, str]] = []
    if cfg:
        raw = getattr(cfg, "steps", None) or getattr(cfg, "transforms", None) or []
        for s in raw:
            sql = getattr(s, "sql", "") or ""
            if sql:
                steps.append({"type": str(getattr(s, "type", "sql")), "sql": sql.strip()})
    all_steps: list[dict[str, str]] = []
    if cfg:
        for s in getattr(cfg, "transforms", None) or []:
            key = getattr(s, "key", None)
            key_str = ", ".join(key) if isinstance(key, list) else (key or "")
            detail = (
                getattr(s, "sql", None)
                or getattr(s, "condition", None)
                or getattr(s, "expression", None)
                or key_str
                or getattr(s, "name", None)
                or ""
            )
            all_steps.append(
                {"type": str(getattr(s, "type", "")), "detail": str(detail).strip()[:140]}
            )
    schedule_str = fmt_cron(cfg.schedule) if cfg and getattr(cfg, "schedule", None) else "—"
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "selected_pipeline": pipeline,
        "steps": steps,
        "all_steps": all_steps,
        "nodes": build_nodes(cfg),
        "transform_types": ["filter", "derive", "deduplicate", "sql"],
        "schedule": schedule_str,
        "source": str(getattr(cfg, "source", "") or "") if cfg else "",
        "destination": str(getattr(cfg, "destination", "") or "") if cfg else "",
        "active_tab": "data",
    }
    return render(request, "data/transforms.html", ctx)


@router.post("/transforms/{pipeline}/add")
def add_transform(
    request: Request,
    eng: WriteDep,
    pipeline: str,
    type_: Annotated[str, Form(alias="type")],
    condition: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    expression: Annotated[str, Form()] = "",
    key: Annotated[str, Form()] = "",
    sql: Annotated[str, Form()] = "",
) -> RedirectResponse:
    step: dict[str, Any] = {"type": type_.strip()}
    if condition.strip():
        step["condition"] = condition.strip()
    if name.strip():
        step["name"] = name.strip()
    if expression.strip():
        step["expression"] = expression.strip()
    if key.strip():
        keys = [k.strip() for k in key.split(",") if k.strip()]
        step["key"] = keys if len(keys) > 1 else keys[0]
    if sql.strip():
        step["sql"] = sql.strip()
    try:
        eng.add_pipeline_transform(pipeline, step)
        flash(request, f"Added {type_.strip()} step to '{pipeline}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


@router.post("/transforms/{pipeline}/delete/{index}")
def delete_transform(
    request: Request, eng: WriteDep, pipeline: str, index: int
) -> RedirectResponse:
    try:
        eng.delete_pipeline_transform(pipeline, index)
        flash(request, f"Removed step {index + 1} from '{pipeline}'.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


@router.get("/transforms/{pipeline}/preview", response_class=HTMLResponse)
def transform_flow_preview(request: Request, eng: ReadDep, pipeline: str) -> HTMLResponse:
    """HTMX partial — the flow canvas with real per-stage row counts (sampled)."""
    cfg = (eng.config.data.pipelines or {}).get(pipeline)
    if cfg is None:
        return HTMLResponse("")
    stages: list[Any] | None = None
    with contextlib.suppress(Exception):
        stages = eng.preview_flow(pipeline).get("stages")
    ctx = base_ctx(request) | {
        "nodes": build_nodes(cfg, stages),
        "selected_pipeline": pipeline,
        "auto_load": False,
    }
    return render(request, "data/flow_canvas.html", ctx)


@router.post("/transforms/{pipeline}/reorder/{index}/{direction}")
def reorder_transform(
    request: Request, eng: WriteDep, pipeline: str, index: int, direction: int
) -> RedirectResponse:
    try:
        eng.reorder_pipeline_transform(pipeline, index, 1 if direction > 0 else -1)
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(f"/data/transforms?pipeline={pipeline}", status_code=303)


# ── Streaming ─────────────────────────────────────────────────────────────────

_STREAMING_TYPES = frozenset(
    {"kafka", "kinesis", "pubsub", "stream", "rabbitmq", "eventhub", "redpanda"}
)


@router.get("/streaming", response_class=HTMLResponse)
def streaming(request: Request, eng: ReadDep) -> HTMLResponse:
    topics = [
        {
            "name": name,
            "type": str(getattr(cfg, "type", "")),
            "path": str(getattr(cfg, "path", None) or getattr(cfg, "broker", None) or ""),
            "status": "active",
        }
        for name, cfg in (eng.config.data.sources or {}).items()
        if str(getattr(cfg, "type", "")).lower() in _STREAMING_TYPES
    ]
    ctx = base_ctx(request) | {
        "topics": topics,
        "active_tab": "data",
    }
    return render(request, "data/streaming.html", ctx)


# ── Asset Graph / Contracts / Templates (stubs) ───────────────────────────────

_DATA_STUB_TITLES = {
    "/data/asset-graph": "Asset Graph",
    "/data/contracts": "Data Contracts",
    "/data/templates": "Pipeline Templates",
}


@router.get("/asset-graph", response_class=HTMLResponse)
@router.get("/contracts", response_class=HTMLResponse)
@router.get("/templates", response_class=HTMLResponse)
def data_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _DATA_STUB_TITLES)


# ── Watermarks ────────────────────────────────────────────────────────────────


@router.get("/watermarks", response_class=HTMLResponse)
def watermarks(request: Request, eng: ReadDep) -> HTMLResponse:
    store = _get_watermark_store(eng)
    rows = store.all_watermarks() if store else []
    sources = list((eng.config.data.sources or {}).keys())
    ctx = base_ctx(request) | {
        "watermarks": rows,
        "all_sources": sources,
        "active_tab": "data",
    }
    return render(request, "data/watermarks.html", ctx)


@router.post("/watermarks/{source}/reset")
def watermark_reset(request: Request, eng: WriteDep, source: str) -> RedirectResponse:
    store = _get_watermark_store(eng)
    if store:
        store.reset(source)
        flash(request, f"Watermark for '{source}' reset — next run will re-ingest all data.")
    return RedirectResponse("/data/watermarks", status_code=303)


# ── Schema contracts + drift ──────────────────────────────────────────────────


def _get_schema_manager(eng: Any) -> Any | None:
    try:
        from dex_studio.scheduler import _get_or_create_studio_db  # type: ignore[attr-defined]
        from dex_studio.schema_evolution import SchemaEvolutionManager
    except ImportError:
        return None
    db = None
    with contextlib.suppress(Exception):
        db = _get_or_create_studio_db(eng)
    if db is None:
        return None
    return SchemaEvolutionManager(eng.project_dir, db)


@router.get("/schema", response_class=HTMLResponse)
def schema_contracts(request: Request, eng: ReadDep) -> HTMLResponse:
    try:
        from dex_studio.scheduler import _get_or_create_studio_db  # type: ignore[attr-defined]
    except ImportError:
        _get_or_create_studio_db = None  # type: ignore[assignment]

    db = None
    if _get_or_create_studio_db is not None:
        with contextlib.suppress(Exception):
            db = _get_or_create_studio_db(eng)
    mgr = _get_schema_manager(eng)
    pipelines = list((eng.config.data.pipelines or {}).keys())
    contracts: list[dict[str, Any]] = []
    drift_events: list[dict[str, Any]] = []
    if db:
        for name in pipelines:
            contract = None
            with contextlib.suppress(Exception):
                contract = db.get_schema_contract(name)
            contracts.append(
                {
                    "pipeline": name,
                    "has_contract": contract is not None,
                    "columns": contract["columns"] if contract else {},
                    "recorded_at": contract.get("recorded_at", "") if contract else "",
                }
            )
    if mgr:
        drift_events = mgr.drift_summary()
    ctx = base_ctx(request) | {
        "contracts": contracts,
        "drift_events": drift_events,
        "pipeline_count": len(pipelines),
        "active_tab": "data",
    }
    return render(request, "data/schema.html", ctx)


@router.post("/schema/{pipeline}/snapshot")
def schema_snapshot(request: Request, eng: WriteDep, pipeline: str) -> RedirectResponse:
    mgr = _get_schema_manager(eng)
    if mgr:
        result = mgr.snapshot_contract(pipeline)
        if result:
            flash(request, f"Schema contract recorded for '{pipeline}' ({len(result)} columns).")
        else:
            flash(request, f"No parquet file found for '{pipeline}'.", "error")
    return RedirectResponse("/data/schema", status_code=303)


@router.post("/schema/drift/{event_id}/accept")
def schema_drift_accept(
    request: Request, eng: WriteDep, event_id: int, pipeline: str = ""
) -> RedirectResponse:
    mgr = _get_schema_manager(eng)
    if mgr and pipeline:
        mgr.accept_drift(event_id, pipeline)
        flash(request, f"Drift accepted — contract updated for '{pipeline}'.")
    return RedirectResponse("/data/schema", status_code=303)


# ── Backfill ──────────────────────────────────────────────────────────────────


def _get_backfill_engine(eng: Any) -> Any | None:
    try:
        from dex_studio.backfill import BackfillEngine
        from dex_studio.scheduler import _get_or_create_studio_db  # type: ignore[attr-defined]
    except ImportError:
        return None
    db = None
    with contextlib.suppress(Exception):
        db = _get_or_create_studio_db(eng)
    if db is None:
        return None
    return BackfillEngine(eng, db)


@router.get("/backfill", response_class=HTMLResponse)
def backfill_page(request: Request, eng: ReadDep) -> HTMLResponse:
    pipelines = list((eng.config.data.pipelines or {}).keys())
    store = _get_watermark_store(eng)
    wm_list = store.all_watermarks() if store else []
    watermark_map = {w["source"]: w["watermark"] for w in wm_list}
    rows: list[dict[str, str]] = []
    for name in pipelines:
        pipe_cfg = (eng.config.data.pipelines or {}).get(name)
        source = str(getattr(pipe_cfg, "source", "") or "") if pipe_cfg else ""
        rows.append(
            {"pipeline": name, "source": source, "watermark": watermark_map.get(source, "")}
        )
    ctx = base_ctx(request) | {
        "pipelines": rows,
        "active_tab": "data",
    }
    return render(request, "data/backfill.html", ctx)


@router.post("/backfill/{pipeline}/trigger")
def backfill_trigger(request: Request, eng: WriteDep, pipeline: str) -> RedirectResponse:
    bf = _get_backfill_engine(eng)
    if bf:
        result = bf.trigger(pipeline, run_now=False)
        if result.get("watermark_reset"):
            flash(
                request,
                f"Backfill queued for '{pipeline}' — watermark reset. Trigger a run to re-ingest.",
            )
        else:
            flash(request, result.get("error") or "Backfill setup failed.", "error")
    return RedirectResponse("/data/backfill", status_code=303)


# ── Pipeline quality rules ─────────────────────────────────────────────────────


def _get_quality_db(eng: Any) -> Any | None:
    try:
        from dex_studio.scheduler import _get_or_create_studio_db  # type: ignore[attr-defined]
    except ImportError:
        return None
    with contextlib.suppress(Exception):
        return _get_or_create_studio_db(eng)
    return None


@router.get("/pipelines/{pipeline_name}/quality", response_class=HTMLResponse)
def pipeline_quality_tab(
    request: Request,
    pipeline_name: str,
    eng: ReadDep,
) -> HTMLResponse:
    db = _get_quality_db(eng)
    rules: list[dict[str, Any]] = db.get_quality_rules(pipeline_name) if db else []

    by_col: dict[str, list[dict[str, Any]]] = {}
    for r in rules:
        by_col.setdefault(r["col_name"], []).append(r)

    columns: list[dict[str, Any]] = []
    for col in by_col:
        col_rules = by_col[col]
        passing = sum(1 for rule in col_rules if rule.get("last_result", True))
        columns.append(
            {
                "name": col,
                "type": "—",
                "nullable": True,
                "constraints": [],
                "rules": col_rules,
                "passing": passing,
                "failing": len(col_rules) - passing,
            }
        )

    ctx = base_ctx(request) | {
        "pipeline_name": pipeline_name,
        "columns": columns,
        "by_col": by_col,
        "total_rules": len(rules),
        "passing_rules": sum(1 for r in rules if r.get("last_result", True)),
        "failing_rules": sum(1 for r in rules if not r.get("last_result", True)),
    }
    return render(request, "data/pipeline_quality.html", ctx)


@router.post("/pipelines/{pipeline_name}/quality/rules", response_class=HTMLResponse)
def add_quality_rule_route(
    request: Request,
    pipeline_name: str,
    _: WriteDep,
    col_name: Annotated[str, Form()],
    rule_type: Annotated[str, Form()],
    on_failure: Annotated[str, Form()] = "warn",
    config_json: Annotated[str, Form()] = "{}",
) -> RedirectResponse:
    import json as _json_mod

    db = _get_quality_db(_)
    config: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        config = _json_mod.loads(config_json)
    if db is not None:
        db.add_quality_rule(pipeline_name, col_name, rule_type, config, on_failure)
    return RedirectResponse(
        f"/data/pipelines/{pipeline_name}?tab=quality",
        status_code=303,
    )


@router.post("/pipelines/{pipeline_name}/quality/rules/{rule_id}/update")
def update_quality_rule_route(
    request: Request,
    pipeline_name: str,
    rule_id: int,
    _: WriteDep,
    on_failure: Annotated[str, Form()] = "warn",
    enabled: Annotated[str, Form()] = "1",
) -> Any:
    from fastapi.responses import JSONResponse

    db = _get_quality_db(_)
    if db is not None:
        db.update_quality_rule(rule_id, config={}, on_failure=on_failure, enabled=enabled == "1")
    return JSONResponse({"ok": True})


@router.post("/pipelines/{pipeline_name}/quality/rules/{rule_id}/delete")
def delete_quality_rule_route(
    request: Request,
    pipeline_name: str,
    rule_id: int,
    _: WriteDep,
) -> RedirectResponse:
    db = _get_quality_db(_)
    if db is not None:
        db.delete_quality_rule(rule_id)
    return RedirectResponse(
        f"/data/pipelines/{pipeline_name}?tab=quality",
        status_code=303,
    )


@router.post("/pipelines/{pipeline_name}/quality/run")
@router.post("/pipelines/{pipeline_name}/quality/run-checks")
def run_quality_checks(
    pipeline_name: str,
    _: WriteDep,
) -> RedirectResponse:
    return RedirectResponse(f"/data/pipelines/{pipeline_name}?tab=quality", status_code=303)
