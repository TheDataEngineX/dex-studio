"""Background job execution for blocking engine work.

Keeps CPU/IO-heavy pipeline runs OFF the asyncio event loop and prevents the
same pipeline from being launched twice concurrently — the two root causes of
the UI freezing when several actions overlap.

Page handlers stay responsive because Starlette runs synchronous ``def`` routes
in its own threadpool; long jobs run here in a *separate* pool so a burst of
pipeline runs can never starve page rendering.

On success, both ``_run`` and ``_run_all`` call ``sdb.set_last_run()`` so the
scheduler's cron check sees the correct last-run timestamp and does not re-fire
a pipeline that was already run manually.

Queue system: max 3 concurrent pipelines, additional runs are queued and
picked up when running ones complete. Status flow: queued -> running -> success/failed/skipped
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _TimeoutError
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from tqdm import tqdm

from dex_studio import run_checks

if TYPE_CHECKING:
    from dataenginex.engine import DexEngine

    from dex_studio.studio_db import PgStudioDb, StudioDb

logger = structlog.get_logger()


def _push_pipeline_toast(eng: Any, name: str, status: str, error_msg: str) -> None:
    """No-op placeholder — toasts now handled via StudioStore."""
    pass


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    """Global safety net: log any exception a background thread would otherwise
    swallow silently (e.g. one raised after a ThreadPoolExecutor future's
    result was already abandoned), so a pipeline run can never go from
    "running" straight to vanishing with zero trace in the logs."""
    logger.error(
        "unhandled exception in background thread",
        thread=args.thread.name if args.thread else "unknown",
        exc_type=str(args.exc_type),
        exc_value=str(args.exc_value),
    )


threading.excepthook = _log_thread_exception


def _post_success_checks(
    eng: DexEngine,
    sdb: StudioDb | PgStudioDb | None,
    name: str,
    rows_input: int,
    rows_output: int,
    log_ctx: str,
) -> None:
    """Run quality checks + row reconciliation after a successful pipeline run.

    Alerts via `sdb.record_alert` when available; otherwise falls back to the
    bare quality-check-with-log behavior this replaces (no db to alert through).
    """
    if sdb is not None:
        run_checks.run_quality_check(eng, sdb, name)
        run_checks.check_row_reconciliation(sdb, name, rows_input, rows_output)
        return
    try:
        eng.quality_check_all_tables()
    except Exception:
        logger.exception(f"quality check failed after {log_ctx}", pipeline=name)


# Queue configuration
_MAX_CONCURRENT = 1  # ponytail: 1 at a time — TMDB pipelines OOM at 3 concurrent with 32G
_MAX_QUEUED = 100    # max queued pipelines
_MIN_FREE_MB = 3_072  # ponytail: 3GB free required — TMDB pipelines are memory hogs
_RUN_ALL_SENTINEL = "__run_all__"
_RUN_TIMEOUT_S = 3_600      # release pipeline from running after 1h
_PIPELINE_TIMEOUT_S = 7_200  # hard timeout for a single pipeline run

# Thread pool for pipeline execution (1 worker = 1 concurrent max)
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dex-job")


def _available_mb() -> int:
    """Return available memory in MB using psutil (cross-platform)."""
    try:
        import psutil

        return int(psutil.virtual_memory().available // (1024 * 1024))
    except Exception:  # noqa: BLE001
        return 999_999  # unknown -> allow (fail open)


def _purge_stale(db: StudioDb | PgStudioDb, timeout_s: int = _RUN_TIMEOUT_S) -> int:
    """Re-queue pipelines stuck in 'running' longer than timeout_s."""
    return db.requeue_stale_running(timeout_s)


def _get_studio_db(eng: Any) -> StudioDb | PgStudioDb | None:
    """Thin wrapper — delegates to the shared get_studio_db() singleton."""
    from dex_studio.studio_db import get_studio_db

    return get_studio_db(eng)


def _build_dependency_graph(eng: Any, db: StudioDb | PgStudioDb) -> dict[str, list[str]]:
    """Dependency DAG for execution order — same source (DB model, YAML
    fallback) as resolve_depends_on, so root selection and downstream
    triggering match what the status/UI display shows.
    """

    pipelines: dict[str, Any] = eng.config.data.pipelines or {}
    dag = {name: list(getattr(p, "depends_on", None) or []) for name, p in pipelines.items()}
    return dag


# ── Public API (used by routers) ───────────────────────────────────────────────


def get_progress(name: str, db: StudioDb | PgStudioDb | None = None) -> tuple[str, int, int] | None:
    """Get progress for a running pipeline.

    Returns (stage_name, current, total) or None if not running.
    """
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return None
        db = _get_studio_db(eng)
        if db is None:
            return None

    status = db.get_queue_status()
    for entry in status["entries"]:
        if entry["pipeline_name"] == name and entry["status"] == "running":
            # Return mock progress since we don't track detailed progress in queue
            # In future, this could query actual pipeline progress
            return ("executing", entry.get("attempts", 1), 3)
    return None


def enqueue_pipeline(
    name: str,
    priority: int = 50,
    triggered_by: str = "manual",
    db: StudioDb | PgStudioDb | None = None,
    eng: Any | None = None,
) -> str:
    """Add a pipeline to the DB-backed queue.

    Returns status: queued, running, or started.
    """
    if eng is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
    if eng is None:
        return "busy"

    if db is None:
        db = _get_studio_db(eng)
    if db is None:
        return "busy"

    # Purge stale running entries first — prevents zombie slots from blocking
    db.requeue_stale_running()

    # Check if already running or queued
    status = db.get_queue_status()
    for entry in status["entries"]:
        if entry["pipeline_name"] == name and entry["status"] in ("running", "queued", "pending"):
            return "running"

    # Check queue capacity
    if status["total"] >= _MAX_QUEUED:
        return "busy"

    # Enqueue with priority
    db.enqueue_pipeline(name, priority=priority, triggered_by=triggered_by)

    # Try to start if slot available
    _start_next_queued(db)
    return "started"


# ── Public API (used by routers) ───────────────────────────────────────────────


def is_pipeline_running(name: str, db: StudioDb | PgStudioDb | None = None) -> bool:
    """True if *name* is currently executing in the background pool."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return False
        db = _get_studio_db(eng)
        if db is None:
            return False

    # Check DB queue for running status
    status = db.get_queue_status()
    return name in [e["pipeline_name"] for e in status["entries"] if e["status"] == "running"]


def is_pipeline_queued(name: str, db: StudioDb | PgStudioDb | None = None) -> bool:
    """True if *name* is waiting in the queue."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return False
        db = _get_studio_db(eng)
        if db is None:
            return False

    status = db.get_queue_status()
    entries = status["entries"]
    return name in [
        e["pipeline_name"]
        for e in entries
        if e["status"] in ("queued", "pending")
    ]


def running_pipelines(db: StudioDb | PgStudioDb | None = None) -> set[str]:
    """Snapshot of pipeline names currently running."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return set()
        db = _get_studio_db(eng)
        if db is None:
            return set()

    status = db.get_queue_status()
    return {e["pipeline_name"] for e in status["entries"] if e["status"] == "running"}


def queued_pipelines(db: StudioDb | PgStudioDb | None = None) -> list[str]:
    """Snapshot of pipeline names currently queued (FIFO order)."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return []
        db = _get_studio_db(eng)
        if db is None:
            return []

    status = db.get_queue_status()
    return [e["pipeline_name"] for e in status["entries"] if e["status"] in ("queued", "pending")]


def get_queue_status(db: StudioDb | PgStudioDb | None = None) -> dict[str, Any]:
    """Get current queue status for monitoring."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return {"running": [], "queued": [], "max_concurrent": _MAX_CONCURRENT}
        db = _get_studio_db(eng)
        if db is None:
            return {"running": [], "queued": [], "max_concurrent": _MAX_CONCURRENT}

    return db.get_queue_status()


def get_run_all_status(db: StudioDb | PgStudioDb | None = None) -> dict[str, Any]:
    """Return run-all session status for the /api/pipelines/run-all/status endpoint.

    Tracks whether a run-all is active, how many pipelines have completed,
    and which are still queued or running.
    """
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return {"active": False, "completed": 0, "total": 0, "pipelines": []}
        db = _get_studio_db(eng)
        if db is None:
            return {"active": False, "completed": 0, "total": 0, "pipelines": []}

    qs = db.get_queue_status()
    entries = qs.get("entries", [])
    running = [e for e in entries if e.get("status") == "running"]
    queued = [e for e in entries if e.get("status") in ("queued", "pending")]
    by_status = qs.get("by_status", {})
    total = qs.get("total", 0)

    # A run-all is active if there are any running or queued entries
    active = bool(running or queued)

    return {
        "active": active,
        "running": [e["pipeline_name"] for e in running],
        "queued": [e["pipeline_name"] for e in queued],
        "completed": by_status.get("success", 0) + by_status.get("failed", 0),
        "total": total,
        "max_concurrent": _MAX_CONCURRENT,
        "free_mb": _available_mb(),
    }


def cancel_pipeline(name: str, db: StudioDb | PgStudioDb | None = None) -> bool:
    """Request cancellation of a pipeline that's pending/queued/running."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return False
        db = _get_studio_db(eng)
        if db is None:
            return False

    return db.cancel_pipeline_in_queue(name)


def is_pipeline_cancelled(name: str, db: StudioDb | PgStudioDb | None = None) -> bool:
    """Check if a pipeline has been requested for cancellation."""
    if db is None:
        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return False
        db = _get_studio_db(eng)
        if db is None:
            return False

    status = db.get_queue_status()
    for e in status["entries"]:
        if e["pipeline_name"] == name:
            return e["error_msg"] and "cancelled" in e["error_msg"]
    return False


# ── Core execution helpers ─────────────────────────────────────────────────────


def _run_pipeline_with_timeout(
    eng: DexEngine,
    name: str,
    timeout_s: int = _PIPELINE_TIMEOUT_S,
    checkpoint_cb: Any | None = None,
) -> Any:
    """Run *eng.run_pipeline(name)* with a hard *timeout_s* ceiling.

    Uses a dedicated thread so a hung pipeline never blocks the pool permanently.
    """
    import concurrent.futures

    def _progress_cb(stage: str, current: int, total: int) -> None:
        # Could store progress in DB if needed
        pass

    _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = _pool.submit(
        eng.run_pipeline, name,
        progress_cb=_progress_cb, checkpoint_cb=checkpoint_cb,
    )
    poll_s = min(30, timeout_s)
    elapsed = 0
    try:
        while True:
            try:
                return fut.result(timeout=poll_s)
            except _TimeoutError:
                elapsed += poll_s
                if elapsed >= timeout_s:
                    logger.error("pipeline run timed out", pipeline=name, timeout_s=timeout_s)
                    raise
                free_mb = _available_mb()
                if free_mb < _MIN_FREE_MB:
                    logger.warning(
                        "pipeline still running under low memory",
                        pipeline=name,
                        free_mb=free_mb,
                        elapsed_s=elapsed,
                    )
                else:
                    logger.info(
                        "pipeline still running",
                        pipeline=name,
                        free_mb=free_mb,
                        elapsed_s=elapsed,
                    )
    except Exception:
        logger.exception("pipeline run failed", pipeline=name)
        raise
    finally:
        _pool.shutdown(wait=False)


def _trigger_dependents(eng: Any, completed_name: str, db: StudioDb | PgStudioDb) -> None:
    """Trigger downstream pipelines whose dependencies are now all satisfied.

    A dependency is "satisfied" if its lakehouse output exists on disk.
    """
    from dataenginex.data.pipeline.dag import downstream_of

    pipelines: dict[str, Any] = eng.config.data.pipelines or {}
    dag = {n: list(getattr(p, "depends_on", None) or []) for n, p in pipelines.items()}

    lake_root = _get_lake_root(eng)

    def _dep_satisfied(dep_name: str) -> bool:
        pipe_cfg = pipelines.get(dep_name)
        if pipe_cfg is None:
            return False
        dest = getattr(pipe_cfg, "destination", "")
        if not dest:
            return True
        target = getattr(pipe_cfg, "target", None)
        if isinstance(target, dict):
            layer = target.get("layer", "")
        else:
            layer = getattr(target, "layer", "") if target else ""
        if layer:
            base = lake_root / layer / pipe_cfg.destination
        else:
            base = lake_root / pipe_cfg.destination
        parquet = base.with_suffix(".parquet").exists()
        delta = base.with_suffix(".delta").exists()
        return bool(base.exists() or parquet or delta)

    for dep in downstream_of(completed_name, dag):
        if dep not in pipelines:
            continue
        deps = dag.get(dep, [])
        if all(_dep_satisfied(d) for d in deps):
            logger.info(
                "cascading downstream pipeline",
                upstream=completed_name,
                pipeline=dep,
            )
            run_pipeline_bg(dep, triggered_by="cascade")
        else:
            logger.info(
                "dependency not satisfied, not cascading",
                upstream=completed_name,
                pipeline=dep,
                deps=deps,
            )


def _get_lake_root(eng: Any) -> Path:
    """Get the absolute lakehouse path from the engine."""
    if hasattr(eng, "pipeline_runner") and hasattr(eng.pipeline_runner, "_data_dir"):
        return Path(eng.pipeline_runner._data_dir)
    config_path = getattr(eng, "config_path", None)
    if config_path:
        return Path(config_path).parent / ".dex" / "lakehouse"
    return Path(".dex/lakehouse")


def _enqueue_all_pipelines(
    eng: Any,
    db: StudioDb | PgStudioDb,
    triggered_by: str = "run-all",
) -> int:
    """Queue all pipelines with dependency tracking.

    Returns number of pipelines enqueued.
    """
    from dataenginex.data.pipeline.dag import topological_order

    pipelines: dict[str, Any] = eng.config.data.pipelines or {}
    if not pipelines:
        return 0

    db = _get_studio_db(eng)  # type: ignore[assignment]
    if db is None:
        return 0
    db_: StudioDb | PgStudioDb = db
    dag = _build_dependency_graph(eng, db_)
    # Validate DAG
    topological_order(dag)

    # First, clear any existing run-all state by requeueing stale running
    db.requeue_stale_running()

    # Enqueue all pipelines
    enqueued = 0
    for name in pipelines:
        deps = dag.get(name, [])
        priority = 100 if not deps else 50  # roots get higher priority
        db.enqueue_pipeline(name, priority=priority, depends_on=deps, triggered_by=triggered_by)
        enqueued += 1

    return enqueued


# ── Public entry points ────────────────────────────────────────────────────────


def queue_all_pipelines_bg(eng: Any | None = None) -> str:
    """Queue all pipelines respecting dependencies and concurrency limit.

    Returns one of:
    - "started"      — queued successfully
    - "running"      — run-all already in progress
    - "busy"         — other jobs queued/running (non run-all)
    - "low_memory"   — < 1 GB available; refusing to prevent OOM
    """
    from dex_studio._engine import get_engine

    free_mb = _available_mb()
    if free_mb < _MIN_FREE_MB:
        logger.warning(
            "pipeline run blocked: low memory",
            available_mb=free_mb,
            threshold_mb=_MIN_FREE_MB,
        )
        return "low_memory"

    if eng is None:
        eng = get_engine()
    if eng is None:
        return "busy"

    db = _get_studio_db(eng)
    if db is None:
        return "busy"

    # Check if run-all already active or other jobs running
    status = db.get_queue_status()
    if status["by_status"].get("running", 0) > 0:
        # Purge stale entries first — zombies block all new work
        db.requeue_stale_running()
        status = db.get_queue_status()
        if status["by_status"].get("running", 0) > 0:
            return "running"

    # Enqueue all pipelines
    count = _enqueue_all_pipelines(eng, db, "run-all")
    if count == 0:
        return "busy"

    # Start initial root pipelines
    _start_next_queued(db)
    return "started"


def run_all_pipelines_bg() -> str:
    """Run all pipelines in dependency order as a single sequential background job.

    DEPRECATED: Use queue_all_pipelines_bg() for concurrent execution with dependencies.

    Returns one of:
    - "started"     — queued
    - "running"     — a run-all is already in flight
    - "busy"        — other jobs queued
    - "low_memory"  — < 3 GB available
    """
    free_mb = _available_mb()
    if free_mb < _MIN_FREE_MB:
        return "low_memory"

    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng is None:
        return "busy"

    db = _get_studio_db(eng)
    if db is None:
        return "busy"

    # Simple check - if anything running, busy
    status = db.get_queue_status()
    if status["by_status"].get("running", 0) > 0:
        db.requeue_stale_running()
        status = db.get_queue_status()
        if status["by_status"].get("running", 0) > 0:
            return "running"

    # This is the old sequential version - kept for compatibility
    _EXECUTOR.submit(_run_all_sequential, eng, db)
    return "started"


def run_pipeline_bg(name: str, triggered_by: str = "manual", eng: Any | None = None) -> str:
    """Launch pipeline *name* in the background queue.

    Returns one of:
    - "started"      — accepted and queued/running
    - "running"      — same pipeline already in flight
    - "queued"       — added to queue, waiting for slot
    - "busy"         — queue full
    - "low_memory"   — < 1 GB available; refusing to prevent OOM
    """
    free_mb = _available_mb()
    if free_mb < _MIN_FREE_MB:
        logger.warning(
            "pipeline run blocked: low memory",
            pipeline=name,
            available_mb=free_mb,
            threshold_mb=_MIN_FREE_MB,
        )
        return "low_memory"

    from dex_studio._engine import get_engine

    if eng is None:
        eng = get_engine()
    if eng is None:
        return "busy"

    db = _get_studio_db(eng)
    if db is None:
        return "busy"

    # Purge stale running entries first — prevents zombie slots from blocking
    db.requeue_stale_running()

    # Check if already running or queued
    status = db.get_queue_status()
    for entry in status["entries"]:
        if entry["pipeline_name"] == name and entry["status"] in ("running", "queued", "pending"):
            return "running"

    # Check queue capacity
    if status["total"] >= _MAX_QUEUED:
        return "busy"

    # Enqueue with priority based on dependencies
    from dataenginex.data.pipeline.dag import root_pipelines

    db = _get_studio_db(eng)
    if db is None:
        return "busy"

    dag = _build_dependency_graph(eng, db)
    is_root = name in root_pipelines(dag)
    priority = 100 if is_root else 50

    db.enqueue_pipeline(name, priority=priority, triggered_by=triggered_by)

    # Try to start if slot available
    _start_next_queued(db)
    return "started"


def _get_scheduler_config(eng: Any) -> tuple[int, int]:
    """Return (max_concurrent, min_free_mb) from engine config or defaults."""
    try:
        scheduler = getattr(eng.config, "scheduler", None)
        if scheduler is not None:
            return int(scheduler.max_concurrent), int(scheduler.min_free_mb)
    except Exception:
        pass
    return _MAX_CONCURRENT, _MIN_FREE_MB


def drain_queue(db: StudioDb | PgStudioDb, max_concurrent: int, min_free_mb: int) -> None:
    """Drain queued pipelines until no more can be started (concurrency/memory)."""
    for _ in range(max_concurrent):
        status = db.get_queue_status()
        queued = status["by_status"].get("queued", 0)
        if queued == 0:
            break
        _start_next_queued(db, max_concurrent, min_free_mb)


def _start_next_queued(
    db: StudioDb | PgStudioDb,
    max_concurrent: int | None = None,
    min_free_mb: int | None = None,
) -> None:
    """Start the next queued pipeline if concurrency slot and memory available."""
    # Purge stale running entries first — prevents zombie slots from blocking
    _purge_stale(db)

    # Check running count
    status = db.get_queue_status()
    running = status["by_status"].get("running", 0)
    if max_concurrent is None:
        max_concurrent = _MAX_CONCURRENT
    if running >= max_concurrent:
        return

    # Check memory before claiming — prevents OOM kills from large IMDB/TMDB datasets
    free_mb = _available_mb()
    if min_free_mb is None:
        min_free_mb = _MIN_FREE_MB
    if free_mb < min_free_mb:
        logger.warning(
            "skipping queue claim: low memory",
            free_mb=free_mb,
            threshold_mb=min_free_mb,
        )
        return

    # Claim next
    claimed = db.claim_next_queued(max_concurrent)
    if claimed:
        logger.info(
            "claimed pipeline from queue",
            pipeline=claimed["pipeline_name"],
            free_mb=free_mb,
        )
        _EXECUTOR.submit(_run, claimed["pipeline_name"], claimed=claimed)


def _init_pipeline_run(
    eng: Any, name: str, claimed: dict[str, Any]
) -> tuple[Any | None, int | None, bool]:
    """Init pipeline run: acquire lock, start_run. Returns (sdb, run_id, lock_acquired)."""
    from dex_studio.studio_db import get_studio_db

    sdb = None
    run_id: int | None = None
    lock_acquired = False
    try:
        sdb = get_studio_db(eng)
        if sdb is not None:
            lock_acquired = sdb.acquire_lock(name)
            if lock_acquired:
                run_id = sdb.start_run(name, triggered_by=claimed.get("triggered_by", "manual"))
    except Exception:
        logger.exception("failed to init studio_db for pipeline", pipeline=name)
    return sdb, run_id, lock_acquired


def _execute_pipeline(
    eng: Any, name: str, sdb: Any, run_id: int | None = None,
) -> tuple[str, str, int, int]:
    """Execute pipeline and return (status, error_msg, rows_input, rows_output)."""
    error_msg = ""
    rows_input = 0
    rows_output = 0

    # Check for cancellation before running
    if is_pipeline_cancelled(name, sdb):
        return "cancelled", "Pipeline cancelled by user", 0, 0

    # Step-level checkpoint callback
    def _checkpoint_cb(stage: str) -> None:
        if sdb is not None:
            try:
                sdb.save_checkpoint(name, stage, run_id)
            except Exception:
                logger.exception("checkpoint save failed", pipeline=name, stage=stage)

    result = _run_pipeline_with_timeout(eng, name, checkpoint_cb=_checkpoint_cb)
    skipped = False
    rows_input = 0
    rows_output = 0
    if result is not None:
        rows_input = getattr(result, "rows_input", 0) or 0
        rows_output = getattr(result, "rows_output", 0) or 0
        skipped = bool(getattr(result, "skipped", False))

    status = "skipped" if skipped else "success"
    logger.info("pipeline complete", pipeline=name, skipped=skipped)

    if not skipped:
        _post_success_checks(eng, sdb, name, rows_input, rows_output, "manual run")
        _trigger_dependents(eng, name, sdb)

    return status, error_msg, rows_input, rows_output


def _finalize_pipeline_run(
    sdb: Any, run_id: int, name: str, status: str, error_msg: str,
    rows_input: int, rows_output: int, duration_s: float = 0.0,
) -> None:
    """Finalize pipeline run in DB and record Prometheus metrics."""
    try:
        if status == "success":
            terminal = "success"
        elif status == "skipped":
            terminal = "skipped"
        else:
            terminal = "failed"
        sdb.finish_run(run_id, terminal, error_msg, rows_input=rows_input, rows_output=rows_output)
        if status == "success":
            sdb.set_last_run(name, datetime.now(UTC))
            # Clear checkpoint on successful completion
            with contextlib.suppress(Exception):
                sdb.clear_checkpoint(name)
    except Exception:
        logger.exception("sdb.finish_run failed", pipeline=name, run_id=run_id)

    # Prometheus metrics
    try:
        from dex_studio.metrics import record_pipeline_run
        record_pipeline_run(
            name, terminal, duration_s,
            rows_input=rows_input, rows_output=rows_output,
        )
    except Exception:
        logger.exception("metrics record failed", pipeline=name)


def _run(name: str, claimed: dict[str, Any]) -> None:
    """Worker body — runs the pipeline and records its terminal status."""
    import time

    from dex_studio._engine import get_engine

    status = "failure"
    error_msg = ""
    run_id: int | None = None
    sdb = None
    rows_input = 0
    rows_output = 0
    start_time = time.monotonic()

    try:
        eng = get_engine()
        if eng is not None:
            sdb, run_id, lock_acquired = _init_pipeline_run(eng, name, claimed)

            if not lock_acquired:
                status = "queued"
                error_msg = "pipeline locked by another run"
                logger.info("pipeline already locked — will retry later", pipeline=name)
            elif is_pipeline_cancelled(name, sdb):
                status = "cancelled"
                error_msg = "Pipeline cancelled by user"
                logger.info("pipeline cancelled before execution", pipeline=name)
            else:
                status, error_msg, rows_input, rows_output = _execute_pipeline(
                    eng, name, sdb, run_id
                )

    except Exception as exc:  # noqa: BLE001 — background worker must never crash the pool
        error_msg = str(exc)
        logger.error("background pipeline failed", pipeline=name, error=error_msg, exc_info=True)
    finally:
        duration_s = time.monotonic() - start_time
        _finalize_run(
            sdb, run_id, name, status, error_msg,
            rows_input, rows_output, duration_s, claimed, lock_acquired
        )
        _schedule_next_queued()

def _finalize_run(
    sdb: Any | None,
    run_id: int | None,
    name: str,
    status: str,
    error_msg: str,
    rows_input: int,
    rows_output: int,
    duration_s: float,
    claimed: dict[str, Any],
    lock_acquired: bool,
) -> None:
    """Finalize a pipeline run: release lock, record metrics, update queue status."""
    if sdb is not None and lock_acquired:
        with contextlib.suppress(Exception):
            sdb.release_lock(name)

    if sdb is not None:
        if lock_acquired and run_id is not None:
            _finalize_pipeline_run(
                sdb, run_id, name, status, error_msg,
                rows_input, rows_output, duration_s,
            )
            from dex_studio._engine import get_engine
            db = _get_studio_db(get_engine())
            if db:
                db.mark_queue_status(
                    claimed["id"],
                    status,
                    error_msg,
                    run_id,
                    claimed["version"],
                )
        elif not lock_acquired:
            from dex_studio._engine import get_engine
            db = _get_studio_db(get_engine())
            if db:
                db.mark_queue_status(
                    claimed["id"],
                    "queued",
                    "pipeline locked by another run",
                    None,
                    claimed["version"],
                )

def _schedule_next_queued() -> None:
    """Start next queued pipeline if capacity available."""
    from dex_studio._engine import get_engine
    eng = get_engine()
    db = _get_studio_db(eng)
    if db:
        _start_next_queued(db)
        try:
            from dex_studio.metrics import update_queue_depth
            qs = db.get_queue_status()
            running = qs["by_status"].get("running", 0)
            queued = qs["by_status"].get("queued", 0) + qs["by_status"].get("pending", 0)
            update_queue_depth(running, queued)
        except Exception:
            pass


def _run_all_sequential(eng: Any, db: StudioDb | PgStudioDb) -> None:
    """Run all pipelines sequentially in dependency order (legacy mode)."""
    from dataenginex.data.pipeline.dag import resolve_execution_order

    from dex_studio.store import get_store

    sdb = _get_studio_db(eng)
    if sdb is None:
        return

    store = get_store()
    failures: list[str] = []
    try:
        dep_graph: dict[str, list[str]] = {
            name: list(p.depends_on) for name, p in eng.config.data.pipelines.items()
        }
        order = resolve_execution_order(dep_graph)
        with tqdm(total=len(order), desc="Running all pipelines", unit="pipeline") as pbar:
            for name in order:
                pbar.set_description(f"Running {name}")
                status, error_msg, run_id, lock_held, rows_in, rows_out = _run_one_pipeline(
                    name, sdb, store, eng, "run-all"
                )
                # Finalize in DB
                if sdb is not None and run_id is not None:
                    if status == "success":
                        terminal = "success"
                    elif status == "skipped":
                        terminal = "skipped"
                    else:
                        terminal = "failed"
                        failures.append(f"{name}: {error_msg}")
                    sdb.finish_run(
                        run_id,
                        terminal,
                        error_msg,
                        rows_input=rows_in,
                        rows_output=rows_out,
                    )
                    if status == "success":
                        sdb.set_last_run(name, datetime.now(UTC))
                pbar.update(1)
        if failures:
            logger.warning("run-all completed with failures", count=len(failures))
    except Exception:
        logger.exception("run-all failed unexpectedly")
    finally:
        if store is not None:
            with contextlib.suppress(Exception):
                store.set_pipeline_status(_RUN_ALL_SENTINEL, "done")


def _run_one_pipeline(
    name: str,
    sdb: StudioDb | PgStudioDb | None,
    store: Any,
    eng: Any,
    triggered_by: str,
) -> tuple[str, str, int | None, bool, int, int]:
    """Run a single pipeline, return (status, error_msg, run_id, lock_held, rows_in, rows_out)."""
    status = "failure"
    error_msg = ""
    run_id: int | None = None
    lock_held = False
    rows_input = 0
    rows_output = 0

    try:
        store.set_pipeline_status(name, "running")
    except Exception:
        logger.exception("store set_pipeline_status failed", pipeline=name)

    try:
        if sdb is not None:
            lock_held = sdb.acquire_lock(name)
            run_id = sdb.start_run(name, triggered_by=triggered_by)
        result = _run_pipeline_with_timeout(eng, name)
        skipped = False
        if result is not None:
            rows_input = getattr(result, "rows_input", 0) or 0
            rows_output = getattr(result, "rows_output", 0) or 0
            skipped = bool(getattr(result, "skipped", False))
        status = "skipped" if skipped else "success"
        logger.info("pipeline complete", pipeline=name, skipped=skipped)
        _post_success_checks(eng, sdb, name, rows_input, rows_output, "pipeline run")
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        logger.error("pipeline failed", pipeline=name, error=error_msg, exc_info=True)
    return status, error_msg, run_id, lock_held, rows_input, rows_output