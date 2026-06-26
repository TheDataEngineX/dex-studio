"""REST JSON API — /api/* endpoints with Pydantic response models.

These endpoints expose the same data as the UI but as machine-readable JSON,
suitable for CI/CD pipelines, monitoring systems, and third-party integrations.
Authentication uses the same session cookie or API token as the UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dex_studio.routers._deps import ReadDep, WriteDep

router = APIRouter(tags=["api"])


# ── Pydantic response models ──────────────────────────────────────────────────


class PipelineOut(BaseModel):
    name: str
    schedule: str | None
    source: str | None
    destination: str | None
    status: str
    last_run: str | None
    next_run: str | None


class SchedulerStatusOut(BaseModel):
    enabled: bool
    paused: bool
    running_pipelines: list[str]
    dead_letter: list[dict[str, Any]]
    pipeline_count: int


class WatermarkOut(BaseModel):
    source: str
    watermark: str | None
    updated_at: str | None
    hash_count: int


class CompactionRunOut(BaseModel):
    pipeline: str
    files_before: int
    files_after: int
    bytes_before: int
    bytes_after: int
    duration_s: float
    ran_at: str


class DriftEventOut(BaseModel):
    id: int
    pipeline: str
    drift: list[dict[str, str]]
    detected_at: str
    accepted: bool


class AlertOut(BaseModel):
    id: int
    event_type: str
    pipeline: str
    message: str
    delivered: bool
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_studio_db(eng: Any) -> Any | None:
    import contextlib

    from dex_studio.scheduler import _get_or_create_studio_db

    with contextlib.suppress(Exception):
        return _get_or_create_studio_db(eng)
    return None


def _next_run(cron: str, last: datetime | None) -> str | None:
    import contextlib
    from datetime import UTC

    from croniter import croniter  # type: ignore[import-untyped]

    with contextlib.suppress(Exception):
        from datetime import datetime as _dt

        base = last if last else _dt(2000, 1, 1, tzinfo=UTC)
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        nxt: _dt = croniter(cron, base).get_next(_dt)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        return nxt.isoformat()
    return None


# ── Scheduler endpoints ───────────────────────────────────────────────────────


@router.get(
    "/scheduler/status",
    response_model=SchedulerStatusOut,
    summary="Scheduler state and pipeline locks",
)
def api_scheduler_status(request: Request, eng: ReadDep) -> SchedulerStatusOut:
    from dex_studio.scheduler import get_scheduler_status

    raw = get_scheduler_status(eng, request.app)
    return SchedulerStatusOut(
        enabled=raw.get("enabled", False),
        paused=raw.get("paused", False),
        running_pipelines=raw.get("locked", []),
        dead_letter=raw.get("dead_letter", []),
        pipeline_count=len(raw.get("pipelines", [])),
    )


@router.post("/scheduler/pause", summary="Pause the scheduler")
def api_scheduler_pause(eng: WriteDep) -> dict[str, str]:
    from dex_studio.scheduler import scheduler_pause

    scheduler_pause(eng)
    return {"status": "paused"}


@router.post("/scheduler/resume", summary="Resume the scheduler")
def api_scheduler_resume(eng: WriteDep) -> dict[str, str]:
    from dex_studio.scheduler import scheduler_resume

    scheduler_resume(eng)
    return {"status": "resumed"}


@router.post("/scheduler/trigger/{pipeline}", summary="Manually trigger a pipeline run")
def api_scheduler_trigger(eng: WriteDep, pipeline: str) -> dict[str, str]:
    from dex_studio.scheduler import scheduler_trigger

    scheduler_trigger(eng, pipeline)
    return {"status": "triggered", "pipeline": pipeline}


# ── Pipeline endpoints ────────────────────────────────────────────────────────


@router.get(
    "/pipelines",
    response_model=list[PipelineOut],
    summary="List all pipelines with status and schedule",
)
def api_pipelines(eng: ReadDep) -> list[PipelineOut]:
    import contextlib

    from dex_studio.scheduler import _get_or_create_studio_db
    from dex_studio.utils import fmt_cron

    pipes = eng.config.data.pipelines or {}
    db = None
    with contextlib.suppress(Exception):
        db = _get_or_create_studio_db(eng)

    results = []
    for name, cfg in pipes.items():
        cron = str(getattr(cfg, "schedule", "") or "")
        last = None
        with contextlib.suppress(Exception):
            last = db.get_last_run(name) if db else None
        last_run = last.isoformat() if last else None
        nxt = _next_run(cron, last) if cron else None
        last_rec = eng.pipeline_last_run(name)
        status = "never"
        if last_rec:
            status = "success" if last_rec.success else "failed"
        results.append(
            PipelineOut(
                name=name,
                schedule=fmt_cron(cron) if cron else None,
                source=str(getattr(cfg, "source", "") or "") or None,
                destination=str(getattr(cfg, "destination", "") or "") or None,
                status=status,
                last_run=last_run,
                next_run=nxt,
            )
        )
    return results


@router.post("/pipelines/{name}/run", summary="Ad-hoc pipeline run")
def api_pipeline_run(eng: WriteDep, name: str) -> dict[str, str]:

    try:
        eng.run_pipeline(name)
        return {"status": "success", "pipeline": name}
    except Exception:
        return {"status": "error", "pipeline": name, "error": "An error occurred"}


@router.post("/pipelines/{name}/backfill", summary="Trigger pipeline backfill")
def api_pipeline_backfill(eng: WriteDep, name: str) -> dict[str, Any]:
    import contextlib

    from dex_studio.backfill import BackfillEngine
    from dex_studio.scheduler import _get_or_create_studio_db

    db = None
    with contextlib.suppress(Exception):
        db = _get_or_create_studio_db(eng)
    if db is None:
        return {"status": "error", "error": "storage unavailable"}
    result = BackfillEngine(eng, db).trigger(name, run_now=False)
    return result


# ── Watermark endpoints ───────────────────────────────────────────────────────


@router.get(
    "/watermarks",
    response_model=list[WatermarkOut],
    summary="All source watermarks and hash counts",
)
def api_watermarks(eng: ReadDep) -> list[WatermarkOut]:
    from dex_studio.watermark import WatermarkStore

    db = _get_studio_db(eng)
    if db is None:
        return []
    store = WatermarkStore(db)
    return [WatermarkOut(**w) for w in store.all_watermarks()]


@router.delete("/watermarks/{source}", summary="Reset watermark (triggers reprocessing)")
def api_watermark_reset(eng: WriteDep, source: str) -> dict[str, str]:
    from dex_studio.watermark import WatermarkStore

    db = _get_studio_db(eng)
    if db:
        WatermarkStore(db).reset(source)
    return {"status": "reset", "source": source}


# ── Compaction endpoints ──────────────────────────────────────────────────────


@router.get(
    "/compaction/status",
    response_model=list[CompactionRunOut],
    summary="Recent compaction run history",
)
def api_compaction_status(eng: ReadDep) -> list[CompactionRunOut]:
    db = _get_studio_db(eng)
    if db is None:
        return []
    return [CompactionRunOut(**r) for r in db.get_compaction_runs(limit=20)]


@router.post("/compaction/run", summary="Trigger manual compaction for all pipelines")
def api_compaction_run(eng: WriteDep) -> dict[str, Any]:
    from dex_studio.compaction import CompactionEngine

    db = _get_studio_db(eng)
    if db is None:
        return {"status": "error", "error": "storage unavailable"}
    engine = CompactionEngine(eng.project_dir, db)
    pipelines = list((eng.config.data.pipelines or {}).keys())
    results = engine.compact_all(pipelines)
    return {"status": "ok", "compacted": len(results), "pipelines": [r.pipeline for r in results]}


# ── Schema / drift endpoints ──────────────────────────────────────────────────


@router.get(
    "/schema/{pipeline}/drift",
    response_model=list[DriftEventOut],
    summary="Detected schema changes vs contract",
)
def api_schema_drift(eng: ReadDep, pipeline: str) -> list[DriftEventOut]:
    db = _get_studio_db(eng)
    if db is None:
        return []
    events = db.get_drift_events(pipeline)
    return [DriftEventOut(**e) for e in events]


@router.post("/schema/{pipeline}/accept", summary="Accept drift as new contract")
def api_schema_accept(eng: WriteDep, pipeline: str) -> dict[str, str]:
    import contextlib

    from dex_studio.schema_evolution import SchemaEvolutionManager

    db = _get_studio_db(eng)
    if db is None:
        return {"status": "error", "error": "storage unavailable"}
    mgr = SchemaEvolutionManager(eng.project_dir, db)
    events = db.get_drift_events(pipeline)
    open_events = [e for e in events if not e["accepted"]]
    for ev in open_events:
        with contextlib.suppress(Exception):
            mgr.accept_drift(ev["id"], pipeline)
    return {"status": "accepted", "pipeline": pipeline, "count": str(len(open_events))}


# ── Alert endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/alerts",
    response_model=list[AlertOut],
    summary="Recent alert events",
)
def api_alerts(eng: ReadDep) -> list[AlertOut]:
    db = _get_studio_db(eng)
    if db is None:
        return []
    return [AlertOut(**a) for a in db.get_alerts(limit=100)]


@router.get("/quality/contracts", summary="All pipeline quality contracts + SLA status")
def api_quality_contracts(eng: ReadDep) -> JSONResponse:
    import contextlib

    db = _get_studio_db(eng)
    result = []
    for name in eng.config.data.pipelines or {}:
        contract = None
        with contextlib.suppress(Exception):
            contract = db.get_schema_contract(name) if db else None
        result.append(
            {
                "pipeline": name,
                "has_contract": contract is not None,
                "columns": contract["columns"] if contract else {},
                "recorded_at": contract.get("recorded_at") if contract else None,
            }
        )
    return JSONResponse(result)
