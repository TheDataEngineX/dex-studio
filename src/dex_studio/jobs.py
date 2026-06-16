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
from pathlib import Path

import structlog

logger = structlog.get_logger()

# max_workers=1 serializes heavy ETL so concurrent runs cannot blow up host memory.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dex-job")
_MAX_INFLIGHT = 8  # back-pressure: reject new runs beyond this many queued/running
_MIN_FREE_MB = 3_072  # refuse to start if < 3 GB available — prevents WSL OOM kill
_running: set[str] = set()
_lock = threading.Lock()


def _available_mb() -> int:
    """Return MemAvailable in MB by reading /proc/meminfo directly (no deps)."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:  # noqa: BLE001
        pass
    return 999_999  # unknown → allow (fail open)


def is_pipeline_running(name: str) -> bool:
    """True if *name* is currently executing in the background pool."""
    with _lock:
        return name in _running


def running_pipelines() -> set[str]:
    """Snapshot of pipeline names currently running."""
    with _lock:
        return set(_running)


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
        if len(_running) >= _MAX_INFLIGHT:
            return "busy"
        _running.add(name)
    from dex_studio.store import get_store

    get_store().set_pipeline_status(name, "running")
    _EXECUTOR.submit(_run, name)
    return "started"


def _run(name: str) -> None:
    """Worker body — runs the pipeline and records its terminal status."""
    import contextlib

    from dex_studio._engine import get_engine
    from dex_studio.store import get_store

    status = "failure"
    try:
        eng = get_engine()
        if eng is not None:
            eng.run_pipeline(name)
            status = "success"
    except Exception as exc:  # noqa: BLE001 — background worker must never crash the pool
        logger.warning("background pipeline failed", pipeline=name, error=str(exc))
    finally:
        with _lock:
            _running.discard(name)
        with contextlib.suppress(Exception):
            get_store().set_pipeline_status(name, status)
