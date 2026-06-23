"""Compaction engine for DEX Studio lakehouse layers.

Compaction merges multiple small parquet files in a layer directory into a
single optimised file, reducing read overhead and improving query latency.

Works on the local filesystem lakehouse at {project_dir}/.dex/lakehouse/.
Each pipeline's data lives in a single parquet file already (written by
dataenginex), so compaction is most useful after backfill or when the engine
has produced many partition files in sub-directories.

Retention deletes files older than a configured cutoff.
"""

from __future__ import annotations

import contextlib
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from dex_studio.studio_db import StudioDb

__all__ = ["CompactionEngine", "RetentionManager", "CompactionResult"]

log = structlog.get_logger().bind(src="compaction")


class CompactionResult:
    """Summary of one compaction run."""

    __slots__ = (
        "pipeline",
        "files_before",
        "files_after",
        "bytes_before",
        "bytes_after",
        "duration_s",
    )

    def __init__(self, pipeline: str) -> None:
        self.pipeline = pipeline
        self.files_before = 0
        self.files_after = 0
        self.bytes_before = 0
        self.bytes_after = 0
        self.duration_s = 0.0

    @property
    def savings_pct(self) -> float:
        if self.bytes_before == 0:
            return 0.0
        return (1 - self.bytes_after / self.bytes_before) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "files_before": self.files_before,
            "files_after": self.files_after,
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "duration_s": round(self.duration_s, 2),
            "savings_pct": round(self.savings_pct, 1),
        }


class CompactionEngine:
    """Merges small parquet files in a layer directory into one optimised file."""

    def __init__(self, project_dir: Path, db: StudioDb) -> None:
        self._root = project_dir / ".dex" / "lakehouse"
        self._db = db

    def _collect_files(self, pipeline: str) -> list[Path]:
        """Find all parquet files belonging to *pipeline* across all layers."""
        files: list[Path] = []
        for layer in ("bronze", "silver", "gold"):
            layer_dir = self._root / layer
            if not layer_dir.exists():
                continue
            files.extend(layer_dir.glob(f"{pipeline}*.parquet"))
            part_dir = layer_dir / pipeline
            if part_dir.is_dir():
                files.extend(part_dir.glob("*.parquet"))
        return files

    def compact_pipeline(self, pipeline: str) -> CompactionResult | None:
        """Compact all parquet files for *pipeline* into a single file."""
        result = CompactionResult(pipeline)
        files = self._collect_files(pipeline)
        if len(files) < 2:
            return None  # Nothing to compact

        result.files_before = len(files)
        result.bytes_before = sum(f.stat().st_size for f in files)

        # Use DuckDB to merge files into the first location
        import duckdb

        dest = files[0]
        t0 = time.monotonic()
        try:
            paths_sql = ", ".join(f"'{p}'" for p in files)
            tmp = dest.parent / f"_compact_tmp_{pipeline}.parquet"
            with duckdb.connect() as conn:
                conn.execute(
                    f"COPY (SELECT * FROM read_parquet([{paths_sql}])) TO '{tmp}' (FORMAT PARQUET)"
                )
            # Rename first — if this fails, sources are still intact
            tmp.rename(dest)
            # Now safe to remove the original source files (skip dest = files[0])
            for f in files[1:]:
                with contextlib.suppress(OSError):
                    f.unlink()
            result.files_after = 1
            result.bytes_after = dest.stat().st_size
            result.duration_s = time.monotonic() - t0

            self._db.record_compaction(
                pipeline,
                result.files_before,
                result.files_after,
                result.bytes_before,
                result.bytes_after,
                result.duration_s,
            )
            log.info(
                "compaction complete",
                pipeline=pipeline,
                files_before=result.files_before,
                bytes_before=result.bytes_before,
                bytes_after=result.bytes_after,
                duration_s=round(result.duration_s, 2),
            )
            return result
        except Exception as exc:
            log.warning("compaction failed", pipeline=pipeline, error=str(exc))
            return None

    def compact_all(self, pipelines: list[str]) -> list[CompactionResult]:
        results = []
        for name in pipelines:
            r = self.compact_pipeline(name)
            if r:
                results.append(r)
        return results


class RetentionManager:
    """Deletes files from the lakehouse older than a retention window."""

    def __init__(self, project_dir: Path) -> None:
        self._root = project_dir / ".dex" / "lakehouse"

    def apply(self, retention_days: int) -> dict[str, int]:
        """Delete parquet files older than *retention_days*. Returns {layer: count}."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        counts: dict[str, int] = {}
        for layer in ("bronze", "silver", "gold"):
            layer_dir = self._root / layer
            if not layer_dir.exists():
                continue
            deleted = 0
            for f in layer_dir.rglob("*.parquet"):
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
                except OSError:
                    continue
                if mtime < cutoff:
                    try:
                        f.unlink()
                        deleted += 1
                        log.info("retention delete", layer=layer, file=f.name)
                    except OSError as exc:
                        log.warning(
                            "retention: could not delete", layer=layer, file=f.name, error=str(exc)
                        )
            if deleted:
                counts[layer] = deleted
        return counts
