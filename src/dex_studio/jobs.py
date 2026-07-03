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
"""

from __future__ import annotations

import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _TimeoutError
from typing import TYPE_CHECKING, Any

import structlog
from tqdm import tqdm

from dex_studio import run_checks

if TYPE_CHECKING:
    from dataenginex.engine import DexEngine

    from dex_studio.store import StudioStore
    from dex_studio.studio_db import PgStudioDb, StudioDb

logger = structlog.get_logger()


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

# max_workers=2 allows 2 concurrent pipelines per pod (3 pods = 6 cluster-wide).
# Increase memory limits in kustomization.yaml accordingly (6Gi/3Gi recommended).
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dex-job")
_MAX_INFLIGHT = 8  # back-pressure: reject new runs beyond this many queued/running
_MIN_FREE_MB = 1_024  # refuse to start if < 1 GB available — K8s container limit
_RUN_ALL_SENTINEL = "__run_all__"  # sentinel key used in _running and store
_running: set[str] = set()
_started_at: dict[str, float] = {}  # name -> time.monotonic() when added to _running
_RUN_TIMEOUT_S = 3_600  # release pipeline from _running after 1h
_PIPELINE_TIMEOUT_S = 7_200  # hard timeout for a single pipeline run (DuckDB, HTTP, etc.)
_lock = threading.Lock()


def _available_mb() -> int:
    """Return available memory in MB using psutil (cross-platform)."""
    try:
        import psutil

        return int(psutil.virtual_memory().available // (1024 * 1024))
    except Exception:  # noqa: BLE001
        return 999_999  # unknown → allow (fail open)


def _purge_stale() -> None:
    """Remove entries from _running that have exceeded _RUN_TIMEOUT_S."""
    now = time.monotonic()
    stale = [
        n
        for n in _running
        if _started_at.get(n) is not None and (now - _started_at[n]) > _RUN_TIMEOUT_S
    ]
    for n in stale:
        logger.warning("pipeline timeout — releasing stuck lock", pipeline=n)
        _running.discard(n)
        _started_at.pop(n, None)


def _run_pipeline_with_timeout(
    eng: DexEngine, name: str, timeout_s: int = _PIPELINE_TIMEOUT_S,
) -> Any:
    """Run *eng.run_pipeline(name)* with a hard *timeout_s* ceiling.

    Uses a dedicated thread so a hung pipeline never blocks the pool permanently.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
        fut = _pool.submit(eng.run_pipeline, name)
        try:
            return fut.result(timeout=timeout_s)
        except _TimeoutError:
            logger.error("pipeline run timed out", pipeline=name, timeout_s=timeout_s)
            raise
        except Exception:
            logger.exception("pipeline run failed", pipeline=name)
            raise


def is_pipeline_running(name: str) -> bool:
    """True if *name* is currently executing in the background pool."""
    with _lock:
        _purge_stale()
        return name in _running


def running_pipelines() -> set[str]:
    """Snapshot of pipeline names currently running."""
    with _lock:
        _purge_stale()
        return set(_running)


def run_all_pipelines_bg() -> str:
    """Run all pipelines in dependency order as a single sequential background job.

    Returns one of:
    - ``"started"``     — queued
    - ``"running"``     — a run-all is already in flight
    - ``"busy"``        — other jobs queued
    - ``"low_memory"``  — < 3 GB available
    """
    free_mb = _available_mb()
    if free_mb < _MIN_FREE_MB:
        return "low_memory"
    with _lock:
        _purge_stale()
        if _RUN_ALL_SENTINEL in _running:
            return "running"
        if _running:
            return "busy"
        _running.add(_RUN_ALL_SENTINEL)
        _started_at[_RUN_ALL_SENTINEL] = time.monotonic()

    from dex_studio.store import get_store

    with contextlib.suppress(Exception):
        get_store().set_pipeline_status(_RUN_ALL_SENTINEL, "running")
    _EXECUTOR.submit(_run_all)
    return "started"


def _run_one_pipeline(
    name: str,
    sdb: StudioDb | PgStudioDb | None,
    store: StudioStore,
    eng: DexEngine,
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
        if result is not None:
            rows_input = getattr(result, "rows_input", 0) or 0
            rows_output = getattr(result, "rows_output", 0) or 0
        status = "success"
        logger.info("pipeline complete", pipeline=name)
        # Run quality checks + row reconciliation after every successful run
        _post_success_checks(eng, sdb, name, rows_input, rows_output, "pipeline run")
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        logger.error("pipeline failed", pipeline=name, error=error_msg, exc_info=True)
    return status, error_msg, run_id, lock_held, rows_input, rows_output


def _finalize_pipeline(
    name: str,
    status: str,
    error_msg: str,
    run_id: int | None,
    lock_held: bool,
    sdb: StudioDb | PgStudioDb | None,
    store: StudioStore,
    rows_input: int = 0,
    rows_output: int = 0,
) -> None:
    """Finalize pipeline run: update status, finish run, set last_run, release lock."""

    with _lock:
        _running.discard(name)
        _started_at.pop(name, None)
    with contextlib.suppress(Exception):
        store.set_pipeline_status(name, status)
    if sdb is not None and run_id is not None:
        with contextlib.suppress(Exception):
            terminal = "success" if status == "success" else "failed"
            sdb.finish_run(
                run_id, terminal, error_msg,
                rows_input=rows_input, rows_output=rows_output,
            )
        if status == "success":
            from datetime import UTC, datetime

            with contextlib.suppress(Exception):
                sdb.set_last_run(name, datetime.now(UTC))
    if lock_held and sdb is not None:
        with contextlib.suppress(Exception):
            sdb.release_lock(name)


def _run_all() -> None:
    """Run all pipelines sequentially in dependency order."""

    from dataenginex.data.pipeline.dag import resolve_execution_order

    from dex_studio._engine import get_engine
    from dex_studio.store import get_store
    from dex_studio.studio_db import get_studio_db

    eng = get_engine()
    if eng is None:
        return
    sdb = None
    with contextlib.suppress(Exception):
        sdb = get_studio_db(eng)
    store = get_store()
    try:
        dep_graph: dict[str, list[str]] = {
            name: list(p.depends_on) for name, p in eng.config.data.pipelines.items()
        }
        order = resolve_execution_order(dep_graph)
        with tqdm(total=len(order), desc="Running all pipelines", unit="pipeline") as pbar:
            for name in order:
                pbar.set_description(f"Running {name}")
                with _lock:
                    _purge_stale()
                    if name in _running:
                        logger.info("run-all: skipping (already running)", pipeline=name)
                        pbar.update(1)
                        continue
                    _running.add(name)
                    _started_at[name] = time.monotonic()
                status, error_msg, run_id, lock_held, rows_input, rows_output = _run_one_pipeline(
                    name, sdb, store, eng, "run-all"
                )
                _finalize_pipeline(
                    name, status, error_msg, run_id, lock_held, sdb, store,
                    rows_input=rows_input, rows_output=rows_output,
                )
                pbar.update(1)
    except Exception:
        logger.exception("run-all failed unexpectedly")
    finally:
        with _lock:
            _running.discard(_RUN_ALL_SENTINEL)
            _started_at.pop(_RUN_ALL_SENTINEL, None)
        try:
            get_store().set_pipeline_status(_RUN_ALL_SENTINEL, "done")
        except Exception:
            logger.exception("store set_pipeline_status for run-all sentinel failed")


def run_pipeline_bg(name: str) -> str:
    """Launch pipeline *name* in the background.

    Returns one of:
    - ``"started"``      — accepted and queued
    - ``"running"``      — same pipeline already in flight
    - ``"busy"``         — too many runs queued (back-pressure)
    - ``"low_memory"``   — < 3 GB available; refusing to prevent WSL OOM crash
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
    with _lock:
        _purge_stale()
        if name in _running:
            return "running"
        if _RUN_ALL_SENTINEL in _running:
            return "busy"
        if len(_running) >= _MAX_INFLIGHT:
            return "busy"
        _running.add(name)
        _started_at[name] = time.monotonic()

    from dex_studio.store import get_store

    with contextlib.suppress(Exception):
        get_store().set_pipeline_status(name, "running")
    _EXECUTOR.submit(_run, name)
    return "started"


def _finalize_run(
    name: str,
    status: str,
    error_msg: str,
    run_id: int | None,
    sdb: Any,
    lock_held: bool,
    rows_input: int,
    rows_output: int,
) -> None:
    from dex_studio.store import get_store

    with _lock:
        _running.discard(name)
        _started_at.pop(name, None)
    try:
        get_store().set_pipeline_status(name, status)
    except Exception:
        logger.exception("store set_pipeline_status failed", pipeline=name)
    if sdb is not None and run_id is not None:
        try:
            sdb.finish_run(
                run_id, "success" if status == "success" else "failed", error_msg,
                rows_input=rows_input, rows_output=rows_output,
            )
        except Exception:
            logger.exception("sdb.finish_run failed", pipeline=name, run_id=run_id)
        if status == "success":
            from datetime import UTC, datetime

            try:
                sdb.set_last_run(name, datetime.now(UTC))
            except Exception:
                logger.exception("sdb.set_last_run failed", pipeline=name)
    if lock_held and sdb is not None:
        try:
            sdb.release_lock(name)
        except Exception:
            logger.exception("sdb.release_lock failed", pipeline=name)


def _run(name: str) -> None:
    """Worker body — runs the pipeline and records its terminal status."""

    from dex_studio._engine import get_engine
    from dex_studio.studio_db import get_studio_db

    status = "failure"
    error_msg = ""
    run_id: int | None = None
    sdb = None
    lock_held = False
    rows_input = 0
    rows_output = 0
    try:
        eng = get_engine()
        if eng is not None:
            try:
                sdb = get_studio_db(eng)
                if sdb is not None:
                    lock_held = sdb.acquire_lock(name)
                    run_id = sdb.start_run(name, triggered_by="manual")
            except Exception:
                logger.exception("failed to init studio_db for pipeline", pipeline=name)
            result = _run_pipeline_with_timeout(eng, name)
            if result is not None:
                rows_input = getattr(result, "rows_input", 0) or 0
                rows_output = getattr(result, "rows_output", 0) or 0
            status = "success"
            # Run quality checks + row reconciliation after every successful manual run
            _post_success_checks(eng, sdb, name, rows_input, rows_output, "manual run")
    except Exception as exc:  # noqa: BLE001 — background worker must never crash the pool
        error_msg = str(exc)
        logger.error("background pipeline failed", pipeline=name, error=error_msg, exc_info=True)
    finally:
        _finalize_run(name, status, error_msg, run_id, sdb, lock_held, rows_input, rows_output)
