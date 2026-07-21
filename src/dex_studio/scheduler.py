"""Background scheduler — cron-driven pipeline runs with DAG dependency chain.

Runs as an asyncio task alongside FastAPI. Every tick:
  1. Reads scheduler config from dex.yaml (hot-reload, no restart needed).
  2. If scheduler.enabled is false or scheduler is paused → skip.
  3. Clears stale pipeline locks (> 2 h old).
  4. Fires root pipelines (no depends_on) that are due per their cron schedule.
  5. On each pipeline success, triggers its direct dependents.
  6. Failed pipelines are retried up to retry.max_attempts then dead-lettered.

Retry state is persisted to StudioDb (pipeline_run_state table) so it
survives app restarts. Run spans are recorded to pipeline_runs for history.

Adaptive tick: instead of a fixed 30 s sleep, the loop sleeps until the
next cron firing (capped at _MAX_TICK_S) so pipelines fire on time without
burning CPU on empty iterations.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path as _Path
from typing import Any

import structlog
import yaml
from croniter import croniter
from dataenginex.data.pipeline.dag import downstream_of, root_pipelines

from dex_studio import run_checks
from dex_studio.studio_db import PgStudioDb, StudioDb, get_studio_db
from dex_studio.watermark import WatermarkStore

log = structlog.get_logger().bind(src="scheduler")

_MAX_TICK_S = 30  # upper bound on adaptive sleep
_MIN_TICK_S = 5  # lower bound — avoid busy-spinning
_LOCK_TIMEOUT_S = 3600  # 1 h — releases locks from crashed runs
_COMPACTION_INTERVAL_S = 86400  # once per day
_COMPACTION_SENTINEL = "__compaction__"  # synthetic "pipeline" key in scheduler_state
_SCHEDULER_TICK_COUNT = 0  # module-level counter for periodic tasks


# ── Config ────────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True, slots=True)
class SchedulerConfig:
    enabled: bool = True
    timezone: str = "UTC"
    max_concurrent: int = 3
    min_free_mb: int = 3072
    retry_attempts: int = 2
    retry_backoff_s: int = 60
    on_complete: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)


def read_scheduler_config(eng: Any) -> SchedulerConfig:
    """Parse the `scheduler:` block from the project's dex.yaml."""
    path = getattr(eng, "config_path", None)
    if path is None:
        return SchedulerConfig()
    try:
        raw: dict[str, Any] = yaml.safe_load(_Path(str(path)).read_text()) or {}
    except Exception as exc:
        log.error("failed to read scheduler config", path=str(path), error=str(exc))
        return SchedulerConfig()
    sched = raw.get("scheduler") or {}
    retry = sched.get("retry") or {}
    return SchedulerConfig(
        enabled=bool(sched.get("enabled", True)),
        timezone=str(sched.get("timezone", "UTC")),
        max_concurrent=int(sched.get("max_concurrent_pipelines", 3)),
        min_free_mb=int(sched.get("min_free_mb", 3072)),
        retry_attempts=int(retry.get("max_attempts", 2)),
        retry_backoff_s=int(retry.get("backoff_seconds", 60)),
        on_complete=dict(sched.get("on_pipeline_complete") or {}),
    )


# ── Cron helpers ──────────────────────────────────────────────────────────────


def _is_due(cron_expr: str, last_run: datetime | None, now: datetime) -> bool:
    """True if the cron has a tick between last_run (or now) and now.

    A pipeline that has never run waits for its *next* natural cron tick
    rather than firing immediately — using ``now`` (not an epoch far in the
    past) as the fallback base means a fresh/never-run pipeline is never
    retroactively "overdue" just because the scheduler happened to boot.
    """
    try:
        base = last_run if last_run else now
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        itr = croniter(cron_expr, base)
        nxt: datetime = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        return nxt <= now
    except Exception as exc:
        log.warning("invalid cron expression", expr=cron_expr, error=str(exc))
        return False


def _secs_until_next(cron_expr: str, last_run: datetime | None, now: datetime) -> float:
    """Seconds until cron fires next. Returns _MAX_TICK_S on any error."""
    try:
        base = last_run if last_run else now
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        itr = croniter(cron_expr, base)
        nxt: datetime = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        return max(0.0, (nxt - now).total_seconds())
    except Exception as exc:
        log.warning("could not compute next cron tick", expr=cron_expr, error=str(exc))
        return float(_MAX_TICK_S)


# ── Studio DB singleton ───────────────────────────────────────────────────────


def _get_or_create_studio_db(eng: Any) -> StudioDb | PgStudioDb | None:
    """Thin wrapper — delegates to the shared get_studio_db() singleton."""
    return get_studio_db(eng)


# ── Core tick logic (synchronous — runs in worker thread) ─────────────────────


def _fire_completion_signals(eng: Any, name: str, cfg: SchedulerConfig) -> None:
    """Fire on_complete signals (ML retrain, AI index refresh)."""
    signals = cfg.on_complete.get(name, {})
    if signals.get("trigger_ml_retrain"):
        try:
            eng.trigger_ml_retrain(signals.get("ml_experiment", ""))
            log.info("ML retrain triggered", pipeline=name)
        except Exception as exc:
            log.warning("ML retrain trigger failed", pipeline=name, error=str(exc))
    if signals.get("trigger_ai_index_refresh"):
        try:
            eng.trigger_ai_index_refresh()
            log.info("AI index refresh triggered", pipeline=name)
        except Exception as exc:
            log.warning("AI index refresh trigger failed", pipeline=name, error=str(exc))


def _post_success_hooks(
    eng: Any,
    name: str,
    db: StudioDb | PgStudioDb,
    cfg: SchedulerConfig,
    dag: dict[str, list[str]],
    run_ts: datetime,
    _visited: frozenset[str] | None = None,
) -> None:
    """Side-effects after a successful pipeline run: watermark, dependents, signals."""
    visited = (_visited or frozenset()) | {name}

    pipe_cfg = (eng.config.data.pipelines or {}).get(name)
    source = str(getattr(pipe_cfg, "source", "") or "") if pipe_cfg else ""
    if source:
        try:
            WatermarkStore(db).advance_watermark(source, run_ts)
        except Exception as exc:
            log.warning("watermark advance failed", pipeline=name, source=source, error=str(exc))

    for dep in downstream_of(name, dag):
        if (eng.config.data.pipelines or {}).get(dep) is None:
            continue
        if dep in visited:
            log.warning("DAG cycle detected — skipping dependent", pipeline=dep, upstream=name)
            continue
        log.info("triggering dependent", pipeline=dep, upstream=name)
        _run_one_pipeline(eng, dep, db, cfg, dag, _visited=visited)

    _fire_completion_signals(eng, name, cfg)


def _run_one_pipeline(
    eng: Any,
    name: str,
    db: StudioDb | PgStudioDb,
    cfg: SchedulerConfig,
    dag: dict[str, list[str]],
    _visited: frozenset[str] | None = None,
) -> None:
    """Run pipeline `name`, persist a run span, trigger dependents on success.

    Retry state is stored in pipeline_run_state (survives restarts). After
    max_attempts the pipeline is dead-lettered and its state cleared.
    """
    if not db.acquire_lock(name):
        log.debug("pipeline already locked — skipping", pipeline=name)
        return

    # Record the attempt (with backoff) before doing any risky work. A hard
    # kill (e.g. OOM SIGKILL) never reaches the except block below, and the
    # Postgres advisory lock backing acquire_lock() releases the instant the
    # killed connection drops — so without this, a crashed run leaves no
    # trace and the next leader refires it immediately, forever. Writing the
    # attempt first means _run_due_pipelines' retrying/dead check gates the
    # next tick even if this process never comes back.
    retry_at = datetime.fromtimestamp(datetime.now(UTC).timestamp() + cfg.retry_backoff_s, tz=UTC)
    attempts = db.increment_attempts(name, retry_at)

    # If repeated hard kills already burned through the attempt budget
    # without ever reaching the except block below, dead-letter here instead
    # of running again — otherwise attempts keeps climbing past the cap with
    # backoff but the pipeline never actually reaches "dead" state.
    if attempts > cfg.retry_attempts:
        db.record_dead_letter(name, "exceeded max attempts (killed before completing)", attempts)
        db.mark_dead(name)
        db.release_lock(name)
        log.warning("pipeline dead-lettered before run", pipeline=name, attempts=attempts)
        return

    run_id = db.start_run(name, triggered_by="scheduler")
    log.info("running scheduled pipeline", pipeline=name, attempt=attempts)
    try:
        result = eng.run_pipeline(name)
        run_ts = datetime.now(UTC)
        rows_input = getattr(result, "rows_input", 0) or 0 if result is not None else 0
        rows_output = getattr(result, "rows_output", 0) or 0 if result is not None else 0
        skipped = bool(getattr(result, "skipped", False)) if result is not None else False
        terminal = "skipped" if skipped else "success"
        db.finish_run(run_id, terminal, rows_input=rows_input, rows_output=rows_output)
        db.set_last_run(name, run_ts)
        db.release_lock(name)
        db.clear_run_state(name)
        log.info("pipeline complete", pipeline=name, skipped=skipped)
        if not skipped:
            run_checks.run_quality_check(eng, db, name)
            run_checks.check_row_reconciliation(db, name, rows_input, rows_output)
        _post_success_hooks(eng, name, db, cfg, dag, run_ts, _visited=_visited)

    except Exception as exc:
        db.finish_run(run_id, "failure", str(exc))
        db.release_lock(name)
        log.warning(
            "pipeline failed",
            pipeline=name,
            attempt=attempts,
            max_attempts=cfg.retry_attempts,
            error=str(exc),
        )
        if attempts >= cfg.retry_attempts:
            db.record_dead_letter(name, str(exc), attempts)
            db.mark_dead(name)
            try:
                msg = f"Pipeline failed after {attempts} attempts: {str(exc)[:100]}"
                db.record_alert("dead_letter", name, msg)
            except Exception as alert_exc:
                log.warning("dead letter alert failed", pipeline=name, error=str(alert_exc))
        else:
            log.info("retry scheduled", pipeline=name, backoff_s=cfg.retry_backoff_s)


def _should_fire(name: str, pipe_cfg: Any, db: StudioDb | PgStudioDb, now: datetime) -> bool:
    """True if this root pipeline is due and not already locked."""
    if not getattr(pipe_cfg, "schedule", ""):
        return False
    if name in db.locked_pipelines():
        log.debug("pipeline already running — skipping scheduled fire", pipeline=name)
        return False
    return _is_due(pipe_cfg.schedule, db.get_last_run(name), now)


def _fire_retries(
    eng: Any,
    cfg: SchedulerConfig,
    db: StudioDb | PgStudioDb,
    dag: dict[str, list[str]],
    pipelines: dict[str, Any],
    now: datetime,
    ran_cb: Callable[[str], None] | None,
) -> None:
    """Fire pipelines that are due for a retry according to DB state."""
    for state in db.all_retry_states():
        name = state["pipeline"]
        if state["state"] != "retrying":
            continue
        retry_at_str = state["next_retry_at"]
        if not retry_at_str:
            continue
        retry_at = datetime.fromisoformat(retry_at_str)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        if now >= retry_at and pipelines.get(name) is not None:
            log.info("retrying pipeline", pipeline=name)
            _run_one_pipeline(eng, name, db, cfg, dag)
            if ran_cb:
                ran_cb(name)


def _maybe_run_compaction(eng: Any, db: StudioDb | PgStudioDb, now: datetime) -> None:
    """Run a lakehouse compaction pass across all pipelines, at most once per

    _COMPACTION_INTERVAL_S. Only called by the scheduler leader (same gating
    as the rest of scheduler_loop), and cheap to call every tick since it
    no-ops until the interval has elapsed.
    """
    last = db.get_last_run(_COMPACTION_SENTINEL)
    if last is not None and (now - last).total_seconds() < _COMPACTION_INTERVAL_S:
        return
    try:
        from dex_studio.compaction import CompactionEngine

        pipelines = list((eng.config.data.pipelines or {}).keys())
        engine = CompactionEngine(eng.project_dir, db)
        results = engine.compact_all(pipelines)
        log.info("scheduled compaction complete", pipelines_compacted=len(results))
    except Exception as exc:
        log.warning("scheduled compaction failed", error=str(exc))
    finally:
        db.set_last_run(_COMPACTION_SENTINEL, now)


def _compute_next_tick(
    db: StudioDb | PgStudioDb,
    dag: dict[str, list[str]],
    pipelines: dict[str, Any],
    now: datetime,
) -> int:
    """Return seconds until the next root pipeline cron fires (min _MIN_TICK_S)."""
    next_wait = float(_MAX_TICK_S)
    for name in root_pipelines(dag):
        schedule = getattr(pipelines.get(name), "schedule", "") or ""
        if not schedule:
            continue
        secs = _secs_until_next(schedule, db.get_last_run(name), now)
        if secs < next_wait:
            next_wait = secs
    return max(_MIN_TICK_S, int(next_wait))


def _reconcile_orphaned_run(
    db: StudioDb | PgStudioDb, name: str, cutoff_iso: str, reason: str
) -> None:
    """Mark *name*'s stuck 'running' run(s) as failed and record an alert."""
    try:
        reconciled = db.reconcile_stale_running_runs(name, cutoff_iso)
    except Exception as exc:
        log.warning("failed to reconcile orphaned running run", pipeline=name, error=str(exc))
        return
    if not reconciled:
        return
    log.warning("reconciled orphaned running run", pipeline=name, count=reconciled, reason=reason)
    try:
        db.record_alert(
            "run_stuck_reconciled", name, f"{reconciled} run(s) marked failed — {reason}"
        )
    except Exception as exc:
        log.warning("run_stuck_reconciled alert failed", pipeline=name, error=str(exc))


def _reconcile_stale_locks(db: StudioDb | PgStudioDb) -> None:
    """Force-clear expired pipeline locks and reconcile their orphaned runs.

    A crashed process or a mid-run restart leaves a pipeline_locks row behind
    forever and its pipeline_runs row stuck at status='running' — the run
    never got a chance to call finish_run(). clear_stale_locks() already
    force-clears the lock after _LOCK_TIMEOUT_S; this also marks that
    pipeline's stuck 'running' run(s) as failed so the UI doesn't show it as
    actively running indefinitely, and records an alert so it's visible.
    """
    cutoff_iso = datetime.fromtimestamp(
        datetime.now(UTC).timestamp() - _LOCK_TIMEOUT_S, tz=UTC
    ).isoformat()
    stale_pipelines = db.stale_locked_pipelines(_LOCK_TIMEOUT_S)
    db.clear_stale_locks(_LOCK_TIMEOUT_S)

    # A pipeline_locks row can vanish before it ever ages past _LOCK_TIMEOUT_S —
    # e.g. the process holding it gets OOM-killed, Postgres immediately drops
    # the session-scoped advisory lock, and nothing deletes the run's 'running'
    # row since finish_run() never ran. acquire_lock() always creates the run
    # row *after* the lock is held, so any 'running' row for a pipeline that
    # currently holds no lock at all is unambiguously orphaned — reconcile it
    # right away instead of waiting out the full timeout.
    now_iso = datetime.now(UTC).isoformat()
    locked_now = set(db.locked_pipelines())
    running_names = {
        r.get("pipeline", "")
        for r in db.get_runs(None, limit=200)
        if r.get("status") == "running" and not r.get("finished_at")
    }
    for name in sorted(running_names - locked_now - set(stale_pipelines)):
        _reconcile_orphaned_run(db, name, now_iso, "status was 'running' but no lock was held")

    for name in stale_pipelines:
        _reconcile_orphaned_run(db, name, cutoff_iso, "run did not report a terminal status")


def resolve_depends_on(eng: Any, db: StudioDb | PgStudioDb, pipeline_name: str) -> list[str]:
    """Pipeline's depends_on — prefers the DB definition model, falls back
    to the YAML-parsed dex.yaml config for projects not yet imported.
    """
    project_id = str(getattr(getattr(eng.config, "project", None), "name", "default") or "default")
    with contextlib.suppress(Exception):
        pdef = db.get_pipeline_def(project_id, pipeline_name)
        if pdef is not None:
            return list(pdef["depends_on"])

    pipes: dict[str, Any] = eng.config.data.pipelines or {}
    pipe_cfg = pipes.get(pipeline_name)
    return list(getattr(pipe_cfg, "depends_on", None) or []) if pipe_cfg else []


def _build_dag(
    eng: Any, db: StudioDb | PgStudioDb, pipelines: dict[str, Any]
) -> dict[str, list[str]]:
    """Dependency DAG for execution order — same source (DB model, YAML
    fallback) as resolve_depends_on, so root selection and downstream
    triggering match what the status/UI display shows.
    """
    return {name: resolve_depends_on(eng, db, name) for name in pipelines}


def _run_due_pipelines(
    eng: Any,
    cfg: SchedulerConfig,
    db: StudioDb | PgStudioDb,
    now: datetime,
    ran_cb: Callable[[str], None] | None = None,
) -> int:
    """Check all root pipelines; run those that are due.

    Returns the number of seconds to sleep before the next check (adaptive
    tick — sleeps until the next cron fires rather than a fixed interval).
    """
    _reconcile_stale_locks(db)
    pipelines: dict[str, Any] = eng.config.data.pipelines or {}
    dag = _build_dag(eng, db, pipelines)

    _fire_retries(eng, cfg, db, dag, pipelines, now, ran_cb)

    # max_concurrent gates against ALL in-flight execution (background API
    # jobs included, via jobs.running_pipelines()), not just this tick's own
    # loop — otherwise an operator capping concurrency at 1 has no effect
    # while a user-triggered background run is already in progress.
    from dex_studio import jobs

    in_flight = len(jobs.running_pipelines())
    for name in root_pipelines(dag):
        if in_flight >= cfg.max_concurrent:
            log.info(
                "max_concurrent_pipelines reached — deferring remaining due pipelines to next tick",
                max_concurrent=cfg.max_concurrent,
            )
            break
        # Resource-aware scheduling: skip if memory is low
        from dex_studio.jobs import _available_mb

        free_mb = _available_mb()
        if free_mb < cfg.min_free_mb:
            log.warning(
                "low memory — deferring pipeline",
                pipeline=name,
                free_mb=free_mb,
                min_free_mb=cfg.min_free_mb,
            )
            break
        pipe_cfg = pipelines.get(name)
        if pipe_cfg is None:
            continue
        state = db.get_run_state(name)
        if state["state"] in ("retrying", "dead"):
            continue
        if _should_fire(name, pipe_cfg, db, now):
            # Use the job queue system which respects max_concurrent
            from dex_studio import jobs

            result = jobs.run_pipeline_bg(name, triggered_by="scheduler")
            if result in ("started", "queued"):
                in_flight += 1
                if ran_cb:
                    ran_cb(name)

    _maybe_run_compaction(eng, db, now)

    # Unconditional queue drain: the loop above only enqueues newly cron-due
    # roots. On a tick where none are due, nothing else was going to attempt
    # to claim already-queued work (that only happened as a side effect of
    # run_pipeline_bg() enqueuing something new, or a run completing) — so a
    # claimed, even top-priority pipeline could sit queued indefinitely with
    # free concurrency slots sitting idle.
    jobs.drain_queue(db, cfg.max_concurrent, cfg.min_free_mb)

    return _compute_next_tick(db, dag, pipelines, now)


# ── Scheduler status ──────────────────────────────────────────────────────────


def _pipeline_sched_row(
    eng: Any,
    name: str,
    pipe_cfg: Any,
    db: StudioDb | PgStudioDb | None,
    locked: list[str],
    dead: list[dict[str, Any]],
    retry_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    last_run = db.get_last_run(name) if db else None
    try:
        last_run_record = eng.store.get_last_pipeline_run(name)
    except Exception as exc:
        log.warning("could not fetch last run record", pipeline=name, error=str(exc))
        last_run_record = None
    status = "never"
    if last_run_record:
        status = "success" if last_run_record.success else "failure"
    if name in locked:
        status = "running"
    retry_state = retry_states.get(name)
    in_dead_letter = any(d["pipeline"] == name for d in dead)
    schedule = getattr(pipe_cfg, "schedule", "") or ""
    next_run_at: str = ""
    if schedule:
        try:
            base = last_run if last_run else datetime.now(UTC)
            itr = croniter(schedule, base)
            nxt = itr.get_next(datetime)
            next_run_at = nxt.replace(tzinfo=UTC).isoformat()
        except Exception as exc:
            log.warning("could not compute next_run_at", pipeline=name, error=str(exc))
    return {
        "name": name,
        "schedule": schedule,
        "depends_on": (
            resolve_depends_on(eng, db, name)
            if db is not None
            else list(getattr(pipe_cfg, "depends_on", None) or [])
        ),
        "last_run_at": last_run.isoformat() if last_run else "",
        "next_run_at": next_run_at,
        "status": status,
        "locked": name in locked,
        "in_dead_letter": in_dead_letter,
        "retry_attempts": retry_state["attempts"] if retry_state else 0,
    }


def get_scheduler_status(eng: Any, app: Any) -> dict[str, Any]:
    """Return scheduler status dict for the API and UI."""
    db = _get_or_create_studio_db(eng)
    sched_cfg = read_scheduler_config(eng) if eng else SchedulerConfig()
    paused = db.is_paused() if db else False
    locked = db.locked_pipelines() if db else []
    dead = db.get_dead_letter() if db else []

    retry_states: dict[str, dict[str, Any]] = {}
    if db:
        for rs in db.all_retry_states():
            retry_states[rs["pipeline"]] = rs

    pipelines_out: list[dict[str, Any]] = []
    if eng:
        pipes: dict[str, Any] = eng.config.data.pipelines or {}
        for name, pipe_cfg in pipes.items():
            pipelines_out.append(
                _pipeline_sched_row(eng, name, pipe_cfg, db, locked, dead, retry_states)
            )

    task: asyncio.Task[None] | None = getattr(getattr(app, "state", None), "scheduler_task", None)
    running = task is not None and not task.done()

    return {
        "enabled": sched_cfg.enabled,
        "paused": paused,
        "running": running,
        "tick_s": _MAX_TICK_S,
        "max_concurrent": sched_cfg.max_concurrent,
        "min_free_mb": sched_cfg.min_free_mb,
        "pipelines": pipelines_out,
        "dead_letter": dead,
        "locked": locked,
    }


# ── Control functions (called by API routes) ──────────────────────────────────


def scheduler_pause(eng: Any) -> None:
    db = _get_or_create_studio_db(eng)
    if db:
        db.set_paused(True)
        log.info("scheduler paused")


def scheduler_resume(eng: Any) -> None:
    db = _get_or_create_studio_db(eng)
    if db:
        db.set_paused(False)
        log.info("scheduler resumed")


def scheduler_trigger(eng: Any, pipeline: str) -> str:
    """Immediately trigger a pipeline via the jobs thread pool."""
    from dex_studio.jobs import run_pipeline_bg

    status = run_pipeline_bg(pipeline)
    log.info("manual trigger", pipeline=pipeline, status=status)
    return status


def scheduler_clear_dead_letter(eng: Any, pipeline: str) -> None:
    from dex_studio.jobs import run_pipeline_bg

    db = _get_or_create_studio_db(eng)
    if db:
        db.clear_dead_letter(pipeline)
        db.clear_run_state(pipeline)
        log.info("dead letter cleared", pipeline=pipeline)
    run_pipeline_bg(pipeline)
    log.info("dead letter retry triggered", pipeline=pipeline)


# ── Main asyncio loop ─────────────────────────────────────────────────────────


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """Asyncio task: run due pipelines until stop_event is set.

    Sleeps adaptively — wakes when the next cron fires rather than on a
    fixed interval.
    """
    from dex_studio._engine import get_engine

    log.info("scheduler started", max_tick_s=_MAX_TICK_S)

    global _SCHEDULER_TICK_COUNT
    while not stop_event.is_set():
        import time as _time

        tick_s = _MAX_TICK_S
        tick_start = _time.monotonic()
        pipelines_count = 0
        try:
            eng = get_engine()
            if eng is not None:
                db = _get_or_create_studio_db(eng)
                if db is not None:
                    sched_cfg = read_scheduler_config(eng)
                    if sched_cfg.enabled and not db.is_paused():
                        pipelines_count = (
                            len(eng.config.data.pipelines or {}) if eng.config.data else 0
                        )
                        tick_s = await asyncio.to_thread(
                            _run_due_pipelines, eng, sched_cfg, db, datetime.now(UTC)
                        )
                    elif not sched_cfg.enabled:
                        log.debug("scheduler disabled in dex.yaml — tick skipped")
        except Exception as exc:
            log.error("scheduler tick error", error=str(exc), exc_info=True)

        _SCHEDULER_TICK_COUNT += 1
        # Periodic cleanup: old hashes every 100 ticks (~50 min at 30s tick)
        if _SCHEDULER_TICK_COUNT % 100 == 0 and db is not None:
            with contextlib.suppress(Exception):
                db.cleanup_old_hashes(keep_days=30)

        tick_ms = round((_time.monotonic() - tick_start) * 1000, 1)
        log.debug("scheduler ticked", pipelines=pipelines_count, ms=tick_ms, next_tick_s=tick_s)

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=float(tick_s))

    log.info("scheduler stopped")


# ── FastAPI lifespan helpers ──────────────────────────────────────────────────


_LEADERSHIP_POLL_S = 30  # how often a follower retries claiming leadership


async def _leadership_poll_loop(app: Any, db: Any, stop_event: asyncio.Event) -> None:
    """Followers periodically retry claiming leadership.

    try_scheduler_leadership() was previously only ever called once at boot —
    if the current leader crashes its session-scoped advisory lock releases
    immediately, but if it merely *hangs* (stuck in a long blocking call
    while still holding its connection open) the lock stays held and no
    follower would ever re-check on its own, silently stopping all scheduled
    pipelines cluster-wide until someone notices and restarts that pod.
    """
    while not stop_event.is_set():
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_LEADERSHIP_POLL_S)
        if stop_event.is_set():
            return
        if db.try_scheduler_leadership():
            log.info("acquired scheduler leadership from a follower poll")
            app.state.scheduler_task = asyncio.create_task(
                scheduler_loop(stop_event), name="dex-scheduler"
            )
            return


def start_scheduler(app: Any) -> None:
    from dex_studio._engine import get_engine

    stop_event = asyncio.Event()
    app.state.scheduler_stop_event = stop_event

    eng = get_engine()
    if eng:
        db = get_studio_db(eng)
        if db and not db.try_scheduler_leadership():
            log.info("not scheduler leader — polling to take over if the leader hangs")
            app.state.scheduler_task = asyncio.create_task(
                _leadership_poll_loop(app, db, stop_event), name="dex-scheduler-follower"
            )
            return
    task: asyncio.Task[None] = asyncio.create_task(scheduler_loop(stop_event), name="dex-scheduler")
    app.state.scheduler_task = task
    log.info("background scheduler started")


async def stop_scheduler(app: Any) -> None:
    stop_event: asyncio.Event | None = getattr(app.state, "scheduler_stop_event", None)
    task: asyncio.Task[None] | None = getattr(app.state, "scheduler_task", None)
    if stop_event:
        stop_event.set()
    if task:
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5.0)
    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng:
        db = get_studio_db(eng)
        if db:
            db.release_scheduler_leadership()
    log.info("background scheduler stopped")
