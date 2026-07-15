"""Pipeline Queue — thin wrapper around DB-backed queue in jobs.py."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog

from dex_studio._engine import get_engine
from dex_studio.jobs import running_pipelines
from dex_studio.scheduler import read_scheduler_config

logger = structlog.get_logger().bind(src="pipeline_queue")

_MAX_CONCURRENT = 3


def get_max_concurrent() -> int:
    """Get max concurrent pipelines from scheduler config, default 3."""
    eng = get_engine()
    if eng:
        cfg = read_scheduler_config(eng)
        return cfg.max_concurrent
    return _MAX_CONCURRENT


def enqueue_pipeline(name: str, triggered_by: str = "manual") -> str:
    """Add a pipeline to the DB-backed queue. Returns status: queued, running, or started."""
    from dex_studio import jobs

    eng = get_engine()
    if not eng:
        return "busy"

    db = jobs._get_studio_db(eng)
    if not db:
        return "busy"

    # Check if already running
    if name in running_pipelines():
        return "running"

    # Check if already queued
    status = db.get_queue_status()
    for entry in status["entries"]:
        if entry["pipeline_name"] == name and entry["status"] in ("queued", "pending"):
            return "queued"

    # Check concurrent limit
    current_running = len(running_pipelines())
    max_concurrent = get_max_concurrent()

    if current_running >= max_concurrent:
        # Enqueue with low priority
        db.enqueue_pipeline(name, priority=50, triggered_by=triggered_by)
        logger.info("pipeline queued", pipeline=name, max_concurrent=max_concurrent)
        return "queued"

    # Can start immediately
    db.enqueue_pipeline(name, priority=100, triggered_by=triggered_by)
    jobs._start_next_queued(db)
    logger.info("pipeline started immediately", pipeline=name)
    return "started"


def get_queue_status() -> dict[str, Any]:
    """Get current queue status from DB."""
    eng = get_engine()
    if not eng:
        return {"queued": [], "running": [], "max_concurrent": _MAX_CONCURRENT}

    from dex_studio import jobs

    db = jobs._get_studio_db(eng)
    if not db:
        return {"queued": [], "running": [], "max_concurrent": _MAX_CONCURRENT}

    return db.get_queue_status()


def mark_pipeline_complete(name: str, success: bool) -> None:
    """Mark a pipeline as complete and try to start next queued."""
    eng = get_engine()
    if not eng:
        return

    from dex_studio import jobs

    db = jobs._get_studio_db(eng)
    if not db:
        return

    status = "success" if success else "failed"
    logger.info("pipeline completed", pipeline=name, status=status)

    # Try to start next queued pipeline
    jobs._start_next_queued(db)


def set_volume_reset_complete(complete: bool = True) -> None:
    """Signal that volume reset is complete - retry logic handled by jobs module."""
    if complete:
        logger.info("volume reset marked complete - jobs module will retry on next enqueue")


def is_volume_reset_complete() -> bool:
    return False


async def queue_processor_loop(stop_event: asyncio.Event) -> None:
    """Background task to process the DB-backed queue and handle retries."""
    logger.info("pipeline queue processor started")

    while not stop_event.is_set():
        try:
            eng = get_engine()
            if eng:
                from dex_studio import jobs

                db = jobs._get_studio_db(eng)
                if db:
                    # Start next queued pipeline if capacity available
                    jobs._start_next_queued(db)
        except Exception as exc:
            logger.error("queue processor error", error=str(exc), exc_info=True)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=5.0)

    logger.info("pipeline queue processor stopped")


def get_queued_pipelines() -> list[dict[str, Any]]:
    """Get list of queued pipelines with details from DB."""
    status = get_queue_status()
    result = []
    for entry in status["entries"]:
        if entry["status"] in ("queued", "pending"):
            result.append({
                "name": entry["pipeline_name"],
                "status": "queued",
                "queued_at": entry.get("created_at"),
                "attempts": entry.get("attempts", 0),
                "triggered_by": entry.get("triggered_by", "manual"),
            })
    return result


def clear_queue() -> None:
    """Clear all queued pipelines from DB."""
    eng = get_engine()
    if not eng:
        return

    from dex_studio import jobs

    db = jobs._get_studio_db(eng)
    if not db:
        return

    status = db.get_queue_status()
    for entry in status["entries"]:
        if entry["status"] in ("queued", "pending"):
            db.cancel_pipeline_in_queue(entry["pipeline_name"])
    logger.info("pipeline queue cleared")