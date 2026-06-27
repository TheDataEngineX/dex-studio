"""Backfill engine for DEX Studio pipelines.

Resets the watermark for a source and re-triggers the pipeline via the
engine so historical data can be re-ingested. Backfill jobs are tracked
in the alert_events table with event_type='backfill' so they appear in
the alerting / activity UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from dex_studio.studio_db import StudioDb
from dex_studio.watermark import WatermarkStore

__all__ = ["BackfillEngine"]

log = structlog.get_logger().bind(src="backfill")


class BackfillEngine:
    """Resets watermarks and re-triggers pipelines for historical re-ingestion."""

    def __init__(self, eng: Any, db: StudioDb) -> None:
        self._eng = eng
        self._db = db
        self._store = WatermarkStore(db)

    def trigger(
        self, pipeline: str, *, clear_hashes: bool = True, run_now: bool = True
    ) -> dict[str, Any]:
        """Reset the pipeline's source watermark and optionally re-run immediately.

        Args:
            pipeline: Pipeline name as defined in dex.yaml.
            clear_hashes: Whether to clear content-hash dedup state (default True).
            run_now: Run the pipeline immediately after reset (default True).

        Returns a status dict with the outcome.
        """
        pipes: dict[str, Any] = self._eng.config.data.pipelines or {}
        pipe_cfg = pipes.get(pipeline)
        source = str(getattr(pipe_cfg, "source", "") or "") if pipe_cfg else ""

        result: dict[str, Any] = {
            "pipeline": pipeline,
            "source": source,
            "watermark_reset": False,
            "run_triggered": False,
            "error": "",
            "started_at": datetime.now(UTC).isoformat(),
        }

        if not pipe_cfg:
            result["error"] = f"Pipeline '{pipeline}' not found in dex.yaml"
            return result

        if source and clear_hashes:
            try:
                self._store.reset(source)
                result["watermark_reset"] = True
                log.info("backfill: watermark reset", pipeline=pipeline, source=source)
            except Exception as exc:
                result["error"] = str(exc)
                log.warning("backfill: watermark reset failed", pipeline=pipeline, error=str(exc))
        elif source:
            try:
                self._db.set_watermark(source, datetime(2000, 1, 1, tzinfo=UTC))
                result["watermark_reset"] = True
            except Exception as exc:
                result["error"] = str(exc)

        # Record in alert_events so it appears in the activity log
        self._db.record_alert(
            "backfill",
            pipeline,
            f"Backfill triggered for '{pipeline}' (source: {source or 'n/a'})",
        )

        if run_now:
            try:
                self._eng.run_pipeline(pipeline)
                result["run_triggered"] = True
                log.info("backfill: pipeline complete", pipeline=pipeline)
            except Exception as exc:
                result["error"] = str(exc)
                log.warning("backfill: pipeline failed", pipeline=pipeline, error=str(exc))

        return result
