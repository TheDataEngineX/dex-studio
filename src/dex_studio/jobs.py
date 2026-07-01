"""Background job execution for blocking engine work.

Keeps CPU/IO-heavy pipeline runs OFF the asyncio event loop and prevents the
same pipeline from being launched twice concurrently — the two root causes of
the UI freezing when several actions overlap.

Page handlers stay responsive because Starlette runs synchronous ``def`` routes
in its own threadpool; long jobs run here in a *separate* pool so a burst of
pipeline runs can never starve page rendering.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import structlog

logger = structlog.get_logger()

# max_workers=1 serializes heavy ETL so concurrent runs cannot blow up host memory.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dex-job")
_MAX_INFLIGHT = 8  # back-pressure: reject new runs beyond this many queued/running
_MIN_FREE_MB = 3_072  # refuse to start if < 3 GB available — prevents WSL OOM kill
_RUN_ALL_SENTINEL = "__run_all__"  # sentinel key used in _running and store
_running: set[str] = set()
_lock = threading.Lock()


def _available_mb() -> int:
    """Return available memory in MB using psutil (cross-platform)."""
    try:
        import psutil

        return int(psutil.virtual_memory().available // (1024 * 1024))
    except Exception:  # noqa: BLE001
        return 999_999  # unknown → allow (fail open)


def is_pipeline_running(name: str) -> bool:
    """True if *name* is currently executing in the background pool."""
    with _lock:
        return name in _running


def running_pipelines() -> set[str]:
    """Snapshot of pipeline names currently running."""
    with _lock:
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
        if _RUN_ALL_SENTINEL in _running:
            return "running"
        if _running:
            return "busy"
        _running.add(_RUN_ALL_SENTINEL)
    import contextlib

    from dex_studio.store import get_store

    with contextlib.suppress(Exception):
        get_store().set_pipeline_status(_RUN_ALL_SENTINEL, "running")
    _EXECUTOR.submit(_run_all)
    return "started"


def _run_all() -> None:
    """Run all pipelines sequentially in dependency order."""
    import contextlib

    from dataenginex.data.pipeline.dag import resolve_execution_order

    from dex_studio._engine import get_engine
    from dex_studio.store import get_store

    try:
        eng = get_engine()
        if eng is None:
            return
        dep_graph: dict[str, list[str]] = {
            name: list(p.depends_on) for name, p in eng.config.data.pipelines.items()
        }
        order = resolve_execution_order(dep_graph)
        for name in order:
            with _lock:
                if name in _running:
                    logger.info("run-all: skipping (already running)", pipeline=name)
                    continue
                _running.add(name)
            status = "failure"
            try:
                with contextlib.suppress(Exception):
                    get_store().set_pipeline_status(name, "running")
                eng.run_pipeline(name)
                status = "success"
                logger.info("run-all: pipeline complete", pipeline=name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("run-all: pipeline failed", pipeline=name, error=str(exc))
            finally:
                with _lock:
                    _running.discard(name)
                with contextlib.suppress(Exception):
                    get_store().set_pipeline_status(name, status)
    finally:
        with _lock:
            _running.discard(_RUN_ALL_SENTINEL)
        with contextlib.suppress(Exception):
            get_store().set_pipeline_status(_RUN_ALL_SENTINEL, "done")


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
        if name in _running:
            return "running"
        if _RUN_ALL_SENTINEL in _running:
            return "busy"
        if len(_running) >= _MAX_INFLIGHT:
            return "busy"
        _running.add(name)
    import contextlib

    from dex_studio.store import get_store

    with contextlib.suppress(Exception):
        get_store().set_pipeline_status(name, "running")
    _EXECUTOR.submit(_run, name)
    return "started"


def _run(name: str) -> None:
    """Worker body — runs the pipeline and records its terminal status."""
    import contextlib

    from dex_studio._engine import get_engine
    from dex_studio.store import get_store
    from dex_studio.studio_db import get_studio_db

    status = "failure"
    error_msg = ""
    run_id: int | None = None
    sdb = None
    lock_held = False
    try:
        eng = get_engine()
        if eng is not None:
            with contextlib.suppress(Exception):
                sdb = get_studio_db(eng)
                if sdb is not None:
                    # Acquire cross-pod lock so manual runs also coordinate
                    lock_held = sdb.acquire_lock(name)
                    run_id = sdb.start_run(name, triggered_by="manual")
            eng.run_pipeline(name)
            status = "success"
    except Exception as exc:  # noqa: BLE001 — background worker must never crash the pool
        error_msg = str(exc)
        logger.warning("background pipeline failed", pipeline=name, error=error_msg)
    finally:
        with _lock:
            _running.discard(name)
        with contextlib.suppress(Exception):
            get_store().set_pipeline_status(name, status)
        if sdb is not None and run_id is not None:
            with contextlib.suppress(Exception):
                sdb.finish_run(run_id, "success" if status == "success" else "failed", error_msg)
        if lock_held and sdb is not None:
            with contextlib.suppress(Exception):
                sdb.release_lock(name)
