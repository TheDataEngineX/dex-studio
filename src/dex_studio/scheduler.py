"""Background scheduler — cron-driven pipeline runs.

Runs as an asyncio task alongside the FastAPI server. Every tick:
  1. Checks which pipelines are due (by cron schedule).
  2. Runs due pipelines and records quality checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Any

import structlog
from croniter import croniter  # type: ignore[import-untyped]

logger = structlog.get_logger()

# How often the loop ticks (seconds). Pipelines with ≤15-min cron fire on the
# nearest tick boundary, so keep this well under the shortest schedule.
_TICK_S = 30


# ── Cron helpers ─────────────────────────────────────────────────────────────


def _is_due(cron_expr: str, last_run: datetime) -> bool:
    """True if the cron schedule has a tick between last_run and now."""
    try:
        now = datetime.now(tz=UTC)
        base = last_run.replace(tzinfo=UTC) if last_run.tzinfo is None else last_run
        itr = croniter(cron_expr, base)
        nxt: datetime = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        return nxt <= now
    except Exception:
        return False


# ── Tick helpers ─────────────────────────────────────────────────────────────


def _run_pipeline_if_due(
    eng: Any,
    name: str,
    cfg: Any,
    last_run: dict[str, datetime],
    epoch: datetime,
    log: Any,
) -> None:
    if not cfg.schedule or not _is_due(cfg.schedule, last_run.get(name, epoch)):
        return
    from dex_studio.jobs import is_pipeline_running

    if is_pipeline_running(name):
        log.debug("skip scheduled run; manual run already in progress", pipeline=name)
        return
    try:
        log.info("running scheduled pipeline", pipeline=name)
        eng.run_pipeline(name)
        last_run[name] = datetime.now(tz=UTC)
        log.info("pipeline complete", pipeline=name)
        try:
            eng.quality_check_all_tables()
        except Exception as qe:
            log.debug("quality check skipped", error=str(qe))
    except Exception as exc:
        log.warning("pipeline failed", pipeline=name, error=str(exc))


def _tick(eng: Any, last_run: dict[str, datetime], epoch: datetime, log: Any) -> None:
    # Heavy full-dataset ETL is OFF by default; opt in with DEX_SCHEDULER_AUTORUN=1.
    # Prevents surprise multi-million-row pipeline runs from exhausting host memory.
    if os.getenv("DEX_SCHEDULER_AUTORUN", "").lower() not in ("1", "true", "yes"):
        return
    pipelines: dict[str, Any] = eng.config.data.pipelines
    for name, cfg in pipelines.items():
        _run_pipeline_if_due(eng, name, cfg, last_run, epoch, log)


# ── Main scheduler loop ───────────────────────────────────────────────────────


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """Asyncio task: run due pipelines until stop_event is set."""
    from dex_studio._engine import get_engine

    # Seed last_run with now so pipelines don't fire on the first tick —
    # they'll run after their full schedule interval elapses from startup.
    now = datetime.now(tz=UTC)
    last_run: dict[str, datetime] = {}
    epoch = now
    log = logger.bind(component="scheduler")
    log.info("scheduler started", tick_s=_TICK_S)

    while not stop_event.is_set():
        try:
            eng = get_engine()
            if eng is not None:
                # Seed any pipelines we haven't seen yet with now so they
                # don't immediately fire on first discovery.
                for name in eng.config.data.pipelines or {}:
                    last_run.setdefault(name, now)
                # Offload the blocking tick (pipeline runs + quality checks)
                # to a worker thread so it never freezes the event loop.
                await asyncio.to_thread(_tick, eng, last_run, epoch, log)
        except Exception as exc:
            log.warning("scheduler tick error", error=str(exc))

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_TICK_S)


# ── FastAPI lifespan helpers ──────────────────────────────────────────────────


def start_scheduler(app: Any) -> None:
    """Start the background scheduler task and store state on app.state."""
    stop_event = asyncio.Event()
    task: asyncio.Task[None] = asyncio.create_task(scheduler_loop(stop_event), name="dex-scheduler")
    app.state.scheduler_stop_event = stop_event
    app.state.scheduler_task = task
    logger.info("background scheduler started")


async def stop_scheduler(app: Any) -> None:
    """Gracefully stop the scheduler (call from lifespan shutdown)."""
    stop_event: asyncio.Event | None = getattr(app.state, "scheduler_stop_event", None)
    task: asyncio.Task[None] | None = getattr(app.state, "scheduler_task", None)
    if stop_event:
        stop_event.set()
    if task:
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
    logger.info("background scheduler stopped")
