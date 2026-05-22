"""Background scheduler — cron-driven pipeline runs + live data generation.

Runs as an asyncio task alongside the FastAPI server. Every tick:
  1. Appends synthetic rows to source CSVs (simulates a live data feed).
  2. Checks which pipelines are due (by cron schedule).
  3. Runs due pipelines and records quality checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from croniter import croniter  # type: ignore[import-untyped]

logger = structlog.get_logger()

# How often the loop ticks (seconds). Pipelines with ≤15-min cron fire on the
# nearest tick boundary, so keep this well under the shortest schedule.
_TICK_S = 30

# ── Synthetic data pools ─────────────────────────────────────────────────────

_GENRES = [
    "Action",
    "Comedy",
    "Drama",
    "Sci-Fi",
    "Thriller",
    "Horror",
    "Romance",
    "Animation",
    "Documentary",
    "Crime",
]
_DIRECTORS = [
    "Denis Villeneuve",
    "Greta Gerwig",
    "Bong Joon-ho",
    "Jordan Peele",
    "Ava DuVernay",
    "Alfonso Cuarón",
    "Park Chan-wook",
    "Celine Sciamma",
]
_ROLES = ["actor", "director", "producer", "writer"]


def _next_id(csv_path: Path, id_col: str) -> int:
    """Return max(id_col) + 1 from a CSV, or 1 if file is empty."""
    try:
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
            if rows:
                return max(int(r.get(id_col, 0) or 0) for r in rows) + 1
    except Exception:
        pass
    return 1


def _atomic_append(path: Path, new_rows: list[list[object]]) -> None:
    """Read CSV, append rows, write atomically via temp-then-rename."""
    tmp = path.with_suffix(".csv.tmp")
    try:
        # Normalize to Unix line endings so DuckDB's CSV sniffer sees consistent format
        content = path.read_text().replace("\r\n", "\n").replace("\r", "\n")
        if content and not content.endswith("\n"):
            content += "\n"
        with tmp.open("w", newline="\n") as f:
            f.write(content)
            writer = csv.writer(f, lineterminator="\n")
            for row in new_rows:
                writer.writerow(row)
        tmp.replace(path)  # atomic on Linux/macOS
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _append_ratings(data_dir: Path, n: int = 2) -> None:
    """Add n synthetic ratings rows to ratings.csv atomically."""
    path = data_dir / "ratings.csv"
    if not path.exists():
        return
    try:
        next_id = _next_id(path, "ratingId")
        movies_path = data_dir / "movies.csv"
        max_movie = 25
        if movies_path.exists():
            with movies_path.open() as f:
                rows = list(csv.DictReader(f))
                if rows:
                    max_movie = max(int(r.get("movieId", 1) or 1) for r in rows)
        new_rows: list[list[object]] = [
            [
                next_id + i,
                random.randint(1, max_movie),
                random.randint(100, 999),
                round(random.uniform(5.0, 10.0), 1),
                int(time.time()) + i,
            ]
            for i in range(n)
        ]
        _atomic_append(path, new_rows)
        logger.debug("synthetic ratings appended", count=n)
    except Exception as exc:
        logger.warning("ratings append failed", error=str(exc))


def _maybe_append_movie(data_dir: Path) -> None:
    """Occasionally add a new movie row (1-in-5 chance per tick)."""
    if random.random() > 0.2:
        return
    path = data_dir / "movies.csv"
    if not path.exists():
        return
    try:
        next_id = _next_id(path, "movieId")
        genre = "|".join(random.sample(_GENRES, k=random.randint(1, 3)))
        row: list[object] = [
            next_id,
            f"Generated Movie {next_id}",
            genre,
            random.randint(2015, 2025),
            round(random.uniform(6.0, 9.5), 1),
            random.randint(10_000, 500_000),
            random.choice(_DIRECTORS),
            "Various",
            90 + random.randint(0, 60),
            "$0",
        ]
        _atomic_append(path, [row])
        logger.debug("synthetic movie appended", movie_id=next_id)
    except Exception as exc:
        logger.warning("movie append failed", error=str(exc))


def _maybe_append_credit(data_dir: Path) -> None:
    """Occasionally add a credit row for a recent movie (1-in-7 chance)."""
    if random.random() > 0.15:
        return
    path = data_dir / "credits.csv"
    movies_path = data_dir / "movies.csv"
    if not path.exists() or not movies_path.exists():
        return
    try:
        next_id = _next_id(path, "creditId")
        with movies_path.open() as f:
            movie_rows = list(csv.DictReader(f))
        if not movie_rows:
            return
        movie_id = movie_rows[-1].get("movieId", 1)
        row: list[object] = [
            next_id,
            movie_id,
            random.choice(_DIRECTORS),
            random.choice(_ROLES),
            "",
        ]
        _atomic_append(path, [row])
        logger.debug("synthetic credit appended", credit_id=next_id)
    except Exception as exc:
        logger.warning("credit append failed", error=str(exc))


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
    data_dir = _find_data_dir(eng)
    if data_dir:
        _append_ratings(data_dir, n=random.randint(1, 3))
        _maybe_append_movie(data_dir)
        _maybe_append_credit(data_dir)
    pipelines: dict[str, Any] = eng.config.data.pipelines
    for name, cfg in pipelines.items():
        _run_pipeline_if_due(eng, name, cfg, last_run, epoch, log)


# ── Main scheduler loop ───────────────────────────────────────────────────────


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    """Asyncio task: generate data + run due pipelines until stop_event is set."""
    from dex_studio._engine import get_engine

    last_run: dict[str, datetime] = {}
    epoch = datetime(2000, 1, 1, tzinfo=UTC)
    log = logger.bind(component="scheduler")
    log.info("scheduler started", tick_s=_TICK_S)

    while not stop_event.is_set():
        try:
            eng = get_engine()
            if eng is not None:
                _tick(eng, last_run, epoch, log)
        except Exception as exc:
            log.warning("scheduler tick error", error=str(exc))

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_TICK_S)


def _find_data_dir(eng: Any) -> Path | None:
    """Return the data directory for the current engine's first CSV source."""
    try:
        for src in eng.config.data.sources.values():
            if src.path:
                p = Path(src.path)
                if p.exists():
                    return p.parent
    except Exception:
        pass
    return None


# ── FastAPI lifespan helpers ──────────────────────────────────────────────────

_stop_event: asyncio.Event | None = None
_task: asyncio.Task[None] | None = None


def start_scheduler() -> None:
    """Start the background scheduler task (call from lifespan startup)."""
    global _stop_event, _task
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(scheduler_loop(_stop_event), name="dex-scheduler")
    logger.info("background scheduler started")


async def stop_scheduler() -> None:
    """Gracefully stop the scheduler (call from lifespan shutdown)."""
    global _stop_event, _task
    if _stop_event:
        _stop_event.set()
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            _task.cancel()
    logger.info("background scheduler stopped")
