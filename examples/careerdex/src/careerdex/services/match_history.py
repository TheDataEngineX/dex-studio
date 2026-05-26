"""Match analysis history — DuckDB-backed persistence for resume matcher sessions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import structlog

__all__ = ["MatchRecord", "MatchHistoryService"]

logger = structlog.get_logger()

_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "match_history.duckdb"


@dataclass
class MatchRecord:
    """One persisted resume-match analysis session."""

    timestamp: str  # ISO-8601
    provider: str
    model: str
    jd_snippet: str  # first 200 chars of JD — display label
    resume_name: str
    overall_score: float
    result_json: str  # serialized MatchResult fields
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def score_label(self) -> str:
        s = self.overall_score
        if s >= 80:
            return "Strong"
        if s >= 60:
            return "Good"
        if s >= 40:
            return "Moderate"
        return "Weak"

    @property
    def ts_display(self) -> str:
        try:
            dt = datetime.fromisoformat(self.timestamp.replace(" ", "T").split(".")[0])
            return dt.strftime("%b %d, %Y %H:%M")
        except Exception:
            return self.timestamp[:16]


class MatchHistoryService:
    """Persist and query resume match history in DuckDB."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db = db_path
        self._init_db()

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db))

    def _init_db(self) -> None:
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS match_history (
                    id          VARCHAR PRIMARY KEY,
                    timestamp   TIMESTAMP,
                    provider    VARCHAR,
                    model       VARCHAR,
                    jd_snippet  VARCHAR,
                    resume_name VARCHAR,
                    overall_score DOUBLE,
                    result_json VARCHAR
                )
            """)

    def save(self, record: MatchRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO match_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    record.id,
                    record.timestamp,
                    record.provider,
                    record.model,
                    record.jd_snippet[:200],
                    record.resume_name,
                    record.overall_score,
                    record.result_json,
                ],
            )
        logger.debug("match_history_saved", id=record.id, score=record.overall_score)

    def list_all(self, limit: int = 50) -> list[MatchRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM match_history ORDER BY timestamp DESC LIMIT ?", [limit]
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get(self, record_id: str) -> MatchRecord | None:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM match_history WHERE id = ?", [record_id]).fetchall()
        if not rows:
            return None
        return _row_to_record(rows[0])

    def delete(self, record_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM match_history WHERE id = ?", [record_id])

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM match_history").fetchone()
        return int(row[0]) if row else 0

    def avg_score(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT AVG(overall_score) FROM match_history").fetchone()
        return round(float(row[0]), 1) if row and row[0] is not None else 0.0

    def best_score(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(overall_score) FROM match_history").fetchone()
        return round(float(row[0]), 1) if row and row[0] is not None else 0.0


def _row_to_record(r: tuple[object, ...]) -> MatchRecord:
    return MatchRecord(
        id=str(r[0]),
        timestamp=str(r[1]),
        provider=str(r[2]),
        model=str(r[3]),
        jd_snippet=str(r[4]),
        resume_name=str(r[5]),
        overall_score=float(r[6]),  # type: ignore[arg-type]
        result_json=str(r[7]),
    )


def make_record(
    *,
    provider: str,
    model: str,
    jd_text: str,
    resume_name: str,
    overall_score: float,
    result_fields: dict[str, object],
) -> MatchRecord:
    """Convenience constructor for saving a MatchResult to history."""
    return MatchRecord(
        timestamp=datetime.utcnow().isoformat(),
        provider=provider,
        model=model,
        jd_snippet=jd_text[:200],
        resume_name=resume_name,
        overall_score=overall_score,
        result_json=json.dumps(result_fields, default=str),
    )
