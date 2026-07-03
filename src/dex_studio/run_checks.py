"""Post-run integrity checks shared by the scheduler and background jobs.

Both `scheduler.py` (cron-driven runs) and `jobs.py` (manual/background runs)
call `eng.quality_check_all_tables()` and record `rows_input`/`rows_output`
after a pipeline finishes. Neither surfaced problems as alerts — a crashed
quality check or a badly broken transform (rows_output collapsing to 0, or
exceeding rows_input) was only ever visible in logs. These helpers turn both
conditions into `db.record_alert(...)` calls, which are pushed automatically
(see `StudioDb.record_alert` / `PgStudioDb.record_alert`).
"""

from __future__ import annotations

from typing import Any

import structlog

from dex_studio.studio_db import PgStudioDb, StudioDb

log = structlog.get_logger().bind(src="run_checks")

_QUALITY_SCORE_THRESHOLD = 1.0  # anything less than a perfect score is flagged
_ROWS_DROP_RATIO_THRESHOLD = 0.5  # >50% row loss looks like a broken transform


def run_quality_check(eng: Any, db: StudioDb | PgStudioDb, pipeline: str) -> None:
    """Run quality checks after a pipeline run; alert on crash or low score.

    - If `quality_check_all_tables()` raises, records a `quality_check_error` alert
      (in addition to the caller's own log line).
    - If it succeeds but this pipeline's destination table scores below
      `_QUALITY_SCORE_THRESHOLD`, records a `quality_check_failed` alert.

    Does not raise — failures to check or to record an alert are logged and
    swallowed, matching the "never let a quality check break a run" behavior
    this replaces.
    """
    try:
        quality_results = eng.quality_check_all_tables() or {}
    except Exception as exc:
        log.warning("quality check failed after pipeline run", pipeline=pipeline, error=str(exc))
        try:
            db.record_alert("quality_check_error", pipeline, str(exc))
        except Exception:
            log.exception("failed to record quality_check_error alert", pipeline=pipeline)
        return

    for tbl, res in quality_results.items():
        if res and tbl.endswith(f".{pipeline}"):
            score = res.get("score", 0)
            if score < _QUALITY_SCORE_THRESHOLD:
                try:
                    db.record_alert("quality_check_failed", pipeline, f"quality score {score}")
                except Exception:
                    log.exception("failed to record quality_check_failed alert", pipeline=pipeline)
            break


def check_row_reconciliation(
    db: StudioDb | PgStudioDb, pipeline: str, rows_input: int, rows_output: int
) -> None:
    """Alert if rows_output looks inconsistent with rows_input for a run.

    Flags:
    - rows_output == 0 while rows_input > 0 (nothing came out of a non-empty run)
    - rows_output > rows_input (output should never exceed input for a straight ingest)
    - drop ratio (rows_input - rows_output) / rows_input > 50% (badly broken transform)

    No-ops if rows_input is 0/negative — there's nothing to reconcile against.
    """
    if not rows_input or rows_input <= 0:
        return

    mismatch = rows_output <= 0 or rows_output > rows_input
    if not mismatch:
        drop_ratio = (rows_input - rows_output) / rows_input
        mismatch = drop_ratio > _ROWS_DROP_RATIO_THRESHOLD

    if mismatch:
        try:
            db.record_alert(
                "reconciliation_mismatch",
                pipeline,
                f"rows_input={rows_input} rows_output={rows_output}",
            )
        except Exception:
            log.exception("failed to record reconciliation_mismatch alert", pipeline=pipeline)
