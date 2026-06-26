"""WatermarkStore — per-source ingestion watermarks and content-hash deduplication.

Watermarks track the latest ingested timestamp per data source so pipelines
can ingest only new data on subsequent runs. Content hashes prevent duplicate
records from being ingested when a source delivers overlapping windows.

State is persisted in StudioDb so it survives application restarts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import structlog

from dex_studio.studio_db import StudioDb

__all__ = ["WatermarkStore"]

log = structlog.get_logger().bind(src="watermark")


class WatermarkStore:
    """Thin facade over StudioDb for watermark and hash-dedup operations."""

    def __init__(self, db: StudioDb) -> None:
        self._db = db

    # ── Watermarks ────────────────────────────────────────────────────────────

    def get_watermark(self, source: str) -> datetime | None:
        """Return the last ingested timestamp for *source*, or None if never set."""
        return self._db.get_watermark(source)

    def set_watermark(self, source: str, ts: datetime) -> None:
        """Advance the watermark for *source* to *ts*."""
        self._db.set_watermark(source, ts)
        log.debug("watermark updated", source=source, ts=ts.isoformat())

    def advance_watermark(self, source: str, candidate: datetime) -> None:
        """Set watermark only if *candidate* is newer than the current value."""
        current = self.get_watermark(source)
        if current is None or candidate > current:
            self.set_watermark(source, candidate)

    def reset(self, source: str) -> None:
        """Clear watermark and all ingested hashes for *source* (triggers full re-ingest)."""
        self._db.reset_watermark(source)
        log.info("watermark reset", source=source)

    def all_watermarks(self) -> list[dict[str, Any]]:
        """Return all watermarks with hash counts, for the UI table."""
        return self._db.all_watermarks()

    # ── Content-hash deduplication ────────────────────────────────────────────

    @staticmethod
    def compute_hash(row: dict[str, Any], columns: list[str] | None = None) -> str:
        """Compute a stable SHA-256 hash for *row*, using *columns* if specified."""
        if columns:
            data = {k: row.get(k) for k in sorted(columns)}
        else:
            data = {k: row[k] for k in sorted(row)}
        canonical = "&".join(f"{k}={v}" for k, v in data.items())
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_duplicate(self, source: str, content_hash: str) -> bool:
        return self._db.is_duplicate(source, content_hash)

    def record_hash(self, source: str, content_hash: str) -> None:
        self._db.record_hash(source, content_hash)
