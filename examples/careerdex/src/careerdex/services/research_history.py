"""Company research history — DuckDB-backed persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import structlog

__all__ = ["ResearchRecord", "ResearchHistoryService"]

logger = structlog.get_logger()

_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "research_history.duckdb"


@dataclass
class ResearchRecord:
    """One persisted company research session."""

    timestamp: str
    company_name: str
    provider: str
    model: str
    result_json: str  # serialized CompanyResearch fields
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def ts_display(self) -> str:
        try:
            dt = datetime.fromisoformat(self.timestamp.replace(" ", "T").split(".")[0])
            return dt.strftime("%b %d, %Y %H:%M")
        except Exception:
            return self.timestamp[:16]


class ResearchHistoryService:
    """Persist and query company research sessions in DuckDB."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db = db_path
        self._init_db()

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db))

    def _init_db(self) -> None:
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_history (
                    id           VARCHAR PRIMARY KEY,
                    timestamp    TIMESTAMP,
                    company_name VARCHAR,
                    provider     VARCHAR,
                    model        VARCHAR,
                    result_json  VARCHAR
                )
            """)

    def save(self, record: ResearchRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO research_history VALUES (?, ?, ?, ?, ?, ?)",
                [
                    record.id,
                    record.timestamp,
                    record.company_name,
                    record.provider,
                    record.model,
                    record.result_json,
                ],
            )
        logger.debug("research_history_saved", company=record.company_name, id=record.id)

    def list_all(self, limit: int = 50) -> list[ResearchRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM research_history ORDER BY timestamp DESC LIMIT ?", [limit]
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get(self, record_id: str) -> ResearchRecord | None:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM research_history WHERE id = ?", [record_id]
            ).fetchall()
        return _row_to_record(rows[0]) if rows else None

    def delete(self, record_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM research_history WHERE id = ?", [record_id])

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM research_history").fetchone()
        return int(row[0]) if row else 0


def _row_to_record(r: tuple[object, ...]) -> ResearchRecord:
    return ResearchRecord(
        id=str(r[0]),
        timestamp=str(r[1]),
        company_name=str(r[2]),
        provider=str(r[3]),
        model=str(r[4]),
        result_json=str(r[5]),
    )


def make_research_record(
    *,
    company_name: str,
    provider: str,
    model: str,
    result_fields: dict[str, object],
) -> ResearchRecord:
    """Convenience constructor for saving a research result."""
    return ResearchRecord(
        timestamp=datetime.utcnow().isoformat(),
        company_name=company_name,
        provider=provider,
        model=model,
        result_json=json.dumps(result_fields, default=str),
    )
