"""Quality contract checker for DEX Studio pipelines.

Reads `quality:` blocks from dex.yaml pipeline configs and checks them
against the actual data in the lakehouse. Results are stored per-run
and surfaced in the /data/quality UI.

Checks supported:
  - completeness   : fraction of non-null values in key columns
  - row_count_min  : minimum expected row count
  - uniqueness     : list of columns that should be unique (no duplicates)
  - freshness_hours: max acceptable age of the latest record
  - custom_sql     : arbitrary SQL returning a single boolean or 0/1 value
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

__all__ = ["QualityChecker", "QualityResult"]

log = structlog.get_logger().bind(src="quality")


class QualityResult:
    """Result of one quality check pass for a single pipeline."""

    __slots__ = ("pipeline", "passed", "score", "checks", "checked_at")

    def __init__(self, pipeline: str) -> None:
        self.pipeline = pipeline
        self.passed = True
        self.score = 1.0
        self.checks: list[dict[str, Any]] = []
        self.checked_at = datetime.now(UTC).isoformat()

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.passed = False

    def compute_score(self) -> None:
        if not self.checks:
            self.score = 1.0
            return
        self.score = sum(1 for c in self.checks if c["passed"]) / len(self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": self.checks,
            "checked_at": self.checked_at,
        }


class QualityChecker:
    """Runs quality contract checks against lakehouse parquet files."""

    def __init__(self, project_dir: Path) -> None:
        self._root = project_dir / ".dex" / "lakehouse"

    def _parquet_path(self, pipeline: str) -> Path | None:
        for layer in ("bronze", "silver", "gold"):
            p = self._root / layer / f"{pipeline}.parquet"
            if p.exists():
                return p
        return None

    def _load(self, path: Path) -> Any:
        import duckdb

        conn = duckdb.connect()
        try:
            conn.execute(f"CREATE VIEW _tbl AS SELECT * FROM read_parquet('{path}')")
        except Exception:
            conn.close()
            raise
        return conn

    def check_pipeline(self, pipeline: str, cfg: Any) -> QualityResult:
        result = QualityResult(pipeline)
        q = getattr(cfg, "quality", None)
        if q is None:
            result.add("no_contract", True, "No quality contract defined — skipping")
            result.compute_score()
            return result

        path = self._parquet_path(pipeline)
        if path is None:
            result.add("file_exists", False, f"No parquet found for pipeline '{pipeline}'")
            result.compute_score()
            return result

        conn = None
        with contextlib.suppress(Exception):
            conn = self._load(path)

        if conn is None:
            result.add("file_readable", False, "Could not open parquet file")
            result.compute_score()
            return result

        try:
            self._check_completeness(result, conn, q)
            self._check_row_count(result, conn, q)
            self._check_uniqueness(result, conn, q)
            self._check_freshness(result, conn, q)
            self._check_custom_sql(result, conn, q)
        finally:
            conn.close()

        result.compute_score()
        return result

    def _check_completeness(self, result: QualityResult, conn: Any, q: Any) -> None:
        threshold = getattr(q, "completeness", None)
        if threshold is None:
            return
        try:
            total = conn.execute("SELECT COUNT(*) FROM _tbl").fetchone()[0]
            if total == 0:
                result.add("completeness", False, "Table is empty")
                return
            nulls = conn.execute(
                "SELECT COUNT(*) FROM _tbl WHERE "
                + " OR ".join(
                    f"CAST({c} AS VARCHAR) IS NULL"
                    for c in [col[0] for col in conn.execute("DESCRIBE _tbl").fetchall()]
                )
            ).fetchone()[0]
            ratio = 1 - (nulls / total)
            passed = ratio >= float(threshold)
            result.add(
                "completeness",
                passed,
                f"{ratio:.1%} non-null (threshold {float(threshold):.1%})",
            )
        except Exception as exc:
            result.add("completeness", False, str(exc))

    def _check_row_count(self, result: QualityResult, conn: Any, q: Any) -> None:
        minimum = getattr(q, "row_count_min", None)
        if minimum is None:
            return
        try:
            count = conn.execute("SELECT COUNT(*) FROM _tbl").fetchone()[0]
            passed = count >= int(minimum)
            result.add("row_count_min", passed, f"{count} rows (min {minimum})")
        except Exception as exc:
            result.add("row_count_min", False, str(exc))

    def _check_uniqueness(self, result: QualityResult, conn: Any, q: Any) -> None:
        columns = getattr(q, "uniqueness", None) or []
        if not columns:
            return
        for col in columns:
            try:
                total = conn.execute("SELECT COUNT(*) FROM _tbl").fetchone()[0]
                distinct = conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM _tbl").fetchone()[0]
                passed = total == distinct
                result.add(
                    f"uniqueness.{col}",
                    passed,
                    f"{distinct}/{total} distinct values",
                )
            except Exception as exc:
                result.add(f"uniqueness.{col}", False, str(exc))

    def _check_freshness(self, result: QualityResult, conn: Any, q: Any) -> None:
        max_hours = getattr(q, "freshness_hours", None)
        if max_hours is None:
            return
        ts_col = None
        with contextlib.suppress(Exception):
            cols = [r[0].lower() for r in conn.execute("DESCRIBE _tbl").fetchall()]
            for candidate in ("updated_at", "created_at", "timestamp", "ingested_at", "date"):
                if candidate in cols:
                    ts_col = candidate
                    break
        if ts_col is None:
            result.add("freshness", False, "No timestamp column found for freshness check")
            return
        try:
            latest_raw = conn.execute(f"SELECT MAX({ts_col}) FROM _tbl").fetchone()[0]
            if latest_raw is None:
                result.add("freshness", False, "No rows — cannot check freshness")
                return
            latest = datetime.fromisoformat(str(latest_raw).replace("Z", "+00:00"))
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=UTC)
            age = datetime.now(UTC) - latest
            threshold = timedelta(hours=float(max_hours))
            passed = age <= threshold
            result.add(
                "freshness",
                passed,
                f"Latest record {age.total_seconds() / 3600:.1f}h ago (max {max_hours}h)",
            )
        except Exception as exc:
            result.add("freshness", False, str(exc))

    def _check_custom_sql(self, result: QualityResult, conn: Any, q: Any) -> None:
        sql = getattr(q, "custom_sql", None)
        if not sql:
            return
        try:
            val = conn.execute(sql).fetchone()
            raw = val[0] if val else None
            passed = bool(raw) if raw is not None else False
            result.add("custom_sql", passed, f"Returned: {raw}")
        except Exception as exc:
            result.add("custom_sql", False, str(exc))

    def check_all(self, pipelines: dict[str, Any]) -> list[QualityResult]:
        results = []
        for name, cfg in pipelines.items():
            try:
                results.append(self.check_pipeline(name, cfg))
            except Exception as exc:
                log.warning("quality check error", pipeline=name, error=str(exc))
        return results
