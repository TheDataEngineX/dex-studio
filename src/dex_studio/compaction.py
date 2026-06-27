"""Compaction engine for DEX Studio lakehouse layers."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from dex_studio.studio_db import StudioDb

__all__ = ["CompactionEngine", "CompactionResult"]

log = structlog.get_logger().bind(src="compaction")


@dataclass
class CompactionResult:
    """Summary of one compaction run."""

    pipeline: str
    files_before: int = 0
    files_after: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    duration_s: float = 0.0

    @property
    def savings_pct(self) -> float:
        if self.bytes_before == 0:
            return 0.0
        return (1 - self.bytes_after / self.bytes_before) * 100


class CompactionEngine:
    """Merges small parquet files in a layer directory into a single optimised file."""

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
        """Merge all parquet files for *pipeline* into a single file.

        Returns None if nothing to compact.
        """
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
        """Compact every pipeline in *pipelines*, returning all successful results."""
        results = []
        for name in pipelines:
            r = self.compact_pipeline(name)
            if r:
                results.append(r)
        return results
