"""DEX Studio-specific persistence — scheduler state, locks, vectors, quality tests.

Dual-backend: SQLite (default, single-pod) or PostgreSQL (DATABASE_URL, multi-pod).
PG uses pg_advisory_lock for cross-pod mutual exclusion.

SQLite connection strategy: thread-local connections with WAL mode + busy_timeout.
PostgreSQL strategy: SQLAlchemy connection pool.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

__all__ = ["StudioDb", "PgStudioDb", "get_studio_db"]

log = structlog.get_logger().bind(src="studio_db")


def _lock_key(name: str) -> int:
    """Deterministic 63-bit positive integer for pg_advisory_lock."""
    import hashlib

    return int(hashlib.sha256(name.encode()).hexdigest()[:16], 16) & 0x7FFFFFFFFFFFFFFF

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_state (
    pipeline    TEXT PRIMARY KEY,
    last_run_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_locks (
    pipeline   TEXT PRIMARY KEY,
    locked_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watermarks (
    source      TEXT PRIMARY KEY,
    watermark   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingested_hashes (
    source      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, content_hash)
);

CREATE TABLE IF NOT EXISTS schema_contracts (
    pipeline    TEXT PRIMARY KEY,
    columns_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_drift_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline    TEXT NOT NULL,
    drift_json  TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    accepted    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS compaction_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline      TEXT NOT NULL,
    files_before  INTEGER NOT NULL DEFAULT 0,
    files_after   INTEGER NOT NULL DEFAULT 0,
    bytes_before  INTEGER NOT NULL DEFAULT 0,
    bytes_after   INTEGER NOT NULL DEFAULT 0,
    duration_s    REAL NOT NULL DEFAULT 0.0,
    ran_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    pipeline    TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT '',
    delivered   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letter_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline    TEXT NOT NULL,
    error       TEXT NOT NULL DEFAULT '',
    attempts    INTEGER NOT NULL DEFAULT 1,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run_state (
    pipeline      TEXT PRIMARY KEY,
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    state         TEXT NOT NULL DEFAULT 'idle'
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline     TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    error        TEXT,
    triggered_by TEXT NOT NULL DEFAULT 'scheduler',
    duration_s   REAL,
    request_id   TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline
    ON pipeline_runs(pipeline, started_at DESC);

CREATE TABLE IF NOT EXISTS ai_traces (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent        TEXT NOT NULL,
    message      TEXT NOT NULL DEFAULT '',
    response     TEXT NOT NULL DEFAULT '',
    latency_ms   REAL NOT NULL DEFAULT 0.0,
    tool_calls   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'ok',
    cached       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_traces_created
    ON ai_traces(created_at DESC);

CREATE TABLE IF NOT EXISTS quality_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline    TEXT NOT NULL,
    col_name    TEXT NOT NULL,
    rule_type   TEXT NOT NULL,
    config      TEXT NOT NULL DEFAULT '{}',
    on_failure  TEXT NOT NULL DEFAULT 'warn',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qr_pipeline ON quality_rules(pipeline);

CREATE TABLE IF NOT EXISTS agent_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL UNIQUE,
    agent_name      TEXT NOT NULL,
    user_message    TEXT NOT NULL DEFAULT '',
    final_answer    TEXT NOT NULL DEFAULT '',
    tool_calls      INTEGER NOT NULL DEFAULT 0,
    total_latency_ms REAL NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'done',
    mode            TEXT NOT NULL DEFAULT 'ask',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS agent_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES agent_runs(run_id),
    step_id         INTEGER NOT NULL,
    step_type       TEXT NOT NULL,
    tool_name       TEXT,
    inputs_json     TEXT NOT NULL DEFAULT '{}',
    output_preview  TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'done',
    duration_ms     REAL,
    tokens          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id, step_id);

CREATE TABLE IF NOT EXISTS embedding_collections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    source_table    TEXT NOT NULL DEFAULT '',
    source_column   TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    vector_count    INTEGER NOT NULL DEFAULT 0,
    dim             INTEGER NOT NULL DEFAULT 0,
    duration_s      REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    built_at        TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_vectors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_name TEXT NOT NULL,
    row_id          INTEGER NOT NULL,
    source_text     TEXT NOT NULL,
    embedding_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_collection
    ON embedding_vectors(collection_name);

CREATE TABLE IF NOT EXISTS quality_tests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    test_type   TEXT NOT NULL,
    col_name    TEXT NOT NULL DEFAULT '',
    threshold   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name      TEXT NOT NULL,
    artifact_path   TEXT NOT NULL,
    stage           TEXT NOT NULL DEFAULT 'development',
    algorithm       TEXT NOT NULL DEFAULT '',
    feature_names   TEXT NOT NULL DEFAULT '[]',
    target          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mre_model ON model_registry_entries(model_name, created_at DESC);
"""


class StudioDb:
    """Thread-safe SQLite store for DEX Studio scheduler state.

    Uses thread-local connections so each thread reuses a single open connection
    rather than opening/closing one per query. WAL mode + busy_timeout lets
    SQLite handle concurrent writers without a Python-level lock.
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._local: threading.local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        """Return this thread's persistent connection, creating it if needed."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._conn()
        for stmt in _SCHEMA.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        conn.commit()

    # ── Scheduler state (last run per pipeline) ───────────────────────────────

    def get_last_run(self, pipeline: str) -> datetime | None:
        row = (
            self._conn()
            .execute("SELECT last_run_at FROM scheduler_state WHERE pipeline=?", [pipeline])
            .fetchone()
        )
        if row is None:
            return None
        ts = datetime.fromisoformat(row[0])
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

    def set_last_run(self, pipeline: str, ts: datetime) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO scheduler_state(pipeline,last_run_at) VALUES(?,?)"
            " ON CONFLICT(pipeline) DO UPDATE SET last_run_at=excluded.last_run_at",
            [pipeline, ts.isoformat()],
        )
        conn.commit()

    # ── Run locking ───────────────────────────────────────────────────────────

    def acquire_lock(self, pipeline: str) -> bool:
        """Acquire a run lock. Returns True if acquired, False if already held."""
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO pipeline_locks(pipeline,locked_at) VALUES(?,?)",
                [pipeline, datetime.now(UTC).isoformat()],
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def release_lock(self, pipeline: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM pipeline_locks WHERE pipeline=?", [pipeline])
        conn.commit()

    def clear_stale_locks(self, timeout_s: int = 7200) -> int:
        cutoff_iso = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() - timeout_s, tz=UTC
        ).isoformat()
        conn = self._conn()
        cur = conn.execute("DELETE FROM pipeline_locks WHERE locked_at < ?", [cutoff_iso])
        conn.commit()
        return cur.rowcount

    def locked_pipelines(self) -> list[str]:
        rows = self._conn().execute("SELECT pipeline FROM pipeline_locks").fetchall()
        return [r[0] for r in rows]

    # ── Persistent retry state ─────────────────────────────────────────────────

    def get_run_state(self, pipeline: str) -> dict[str, Any]:
        row = (
            self._conn()
            .execute(
                "SELECT attempts, next_retry_at, state FROM pipeline_run_state WHERE pipeline=?",
                [pipeline],
            )
            .fetchone()
        )
        if row is None:
            return {"attempts": 0, "next_retry_at": None, "state": "idle"}
        return {
            "attempts": row[0],
            "next_retry_at": row[1],
            "state": row[2],
        }

    def increment_attempts(self, pipeline: str, next_retry_at: datetime) -> int:
        conn = self._conn()
        conn.execute(
            "INSERT INTO pipeline_run_state(pipeline, attempts, next_retry_at, state)"
            " VALUES(?, 1, ?, 'retrying')"
            " ON CONFLICT(pipeline) DO UPDATE SET"
            "   attempts = attempts + 1,"
            "   next_retry_at = excluded.next_retry_at,"
            "   state = 'retrying'",
            [pipeline, next_retry_at.isoformat()],
        )
        conn.commit()
        row = conn.execute(
            "SELECT attempts FROM pipeline_run_state WHERE pipeline=?", [pipeline]
        ).fetchone()
        return int(row[0]) if row else 1

    def mark_dead(self, pipeline: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO pipeline_run_state(pipeline, attempts, next_retry_at, state)"
            " VALUES(?, 0, NULL, 'dead')"
            " ON CONFLICT(pipeline) DO UPDATE SET"
            "   next_retry_at = NULL, state = 'dead'",
            [pipeline],
        )
        conn.commit()

    def clear_run_state(self, pipeline: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM pipeline_run_state WHERE pipeline=?", [pipeline])
        conn.commit()

    def all_retry_states(self) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT pipeline, attempts, next_retry_at, state"
                " FROM pipeline_run_state WHERE state != 'idle'"
            )
            .fetchall()
        )
        return [
            {"pipeline": r[0], "attempts": r[1], "next_retry_at": r[2], "state": r[3]} for r in rows
        ]

    # ── Pipeline run history (spans) ──────────────────────────────────────────

    def start_run(
        self,
        pipeline: str,
        triggered_by: str = "scheduler",
        request_id: str = "",
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO pipeline_runs(pipeline, started_at, status, triggered_by, request_id)"
            " VALUES(?, ?, 'running', ?, ?)",
            # Strip tz suffix — SQLite julianday() rejects "+00:00" and returns NULL.
            [
                pipeline,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f"),
                triggered_by,
                request_id or "",
            ],
        )
        conn.commit()
        return cur.lastrowid or 0

    def finish_run(
        self,
        run_id: int,
        status: str,
        error: str = "",
    ) -> None:
        # Strip tz suffix — SQLite julianday() rejects "+00:00" and returns NULL.
        finished = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")
        conn = self._conn()
        conn.execute(
            "UPDATE pipeline_runs SET finished_at=?, status=?, error=?,"
            " duration_s = (julianday(?) - julianday(started_at)) * 86400"
            " WHERE id=?",
            [finished, status, error or "", finished, run_id],
        )
        conn.commit()

    def get_runs(
        self,
        pipeline: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        if pipeline:
            rows = conn.execute(
                "SELECT id,pipeline,started_at,finished_at,status,error,"
                "triggered_by,duration_s,request_id"
                " FROM pipeline_runs WHERE pipeline=?"
                " ORDER BY started_at DESC LIMIT ?",
                [pipeline, limit],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,pipeline,started_at,finished_at,status,error,"
                "triggered_by,duration_s,request_id"
                " FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        return [
            {
                "id": r[0],
                "pipeline": r[1],
                "started_at": r[2],
                "finished_at": r[3],
                "status": r[4],
                "error": r[5] or "",
                "triggered_by": r[6],
                "duration_s": round(r[7], 2) if r[7] is not None else None,
                "request_id": r[8] or "",
            }
            for r in rows
        ]

    def prune_runs(self, keep: int = 1000) -> int:
        """Delete oldest runs beyond `keep` rows."""
        conn = self._conn()
        cur = conn.execute(
            "DELETE FROM pipeline_runs WHERE id NOT IN"
            " (SELECT id FROM pipeline_runs ORDER BY started_at DESC LIMIT ?)",
            [keep],
        )
        conn.commit()
        return cur.rowcount

    # ── Dead letter ───────────────────────────────────────────────────────────

    def record_dead_letter(self, pipeline: str, error: str, attempts: int) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM dead_letter_runs WHERE pipeline=?", [pipeline])
        conn.execute(
            "INSERT INTO dead_letter_runs(pipeline,error,attempts,recorded_at) VALUES(?,?,?,?)",
            [pipeline, error, attempts, datetime.now(UTC).isoformat()],
        )
        conn.commit()
        log.warning(
            "pipeline moved to dead letter",
            pipeline=pipeline,
            attempts=attempts,
            error=error[:120],
        )

    def get_dead_letter(self) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT pipeline,error,attempts,recorded_at FROM dead_letter_runs"
                " ORDER BY recorded_at DESC"
            )
            .fetchall()
        )
        return [
            {"pipeline": r[0], "error": r[1], "attempts": r[2], "recorded_at": r[3]} for r in rows
        ]

    def clear_dead_letter(self, pipeline: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM dead_letter_runs WHERE pipeline=?", [pipeline])
        conn.commit()

    # ── Pause state ───────────────────────────────────────────────────────────

    def is_paused(self) -> bool:
        row = (
            self._conn()
            .execute("SELECT value FROM scheduler_settings WHERE key='paused'")
            .fetchone()
        )
        return row is not None and row[0] == "1"

    def set_paused(self, paused: bool) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO scheduler_settings(key,value) VALUES('paused',?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ["1" if paused else "0"],
        )
        conn.commit()

    # ── Watermarks ────────────────────────────────────────────────────────────

    def get_watermark(self, source: str) -> datetime | None:
        row = (
            self._conn()
            .execute("SELECT watermark FROM watermarks WHERE source=?", [source])
            .fetchone()
        )
        if row is None:
            return None
        ts = datetime.fromisoformat(row[0])
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

    def set_watermark(self, source: str, ts: datetime) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO watermarks(source,watermark,updated_at) VALUES(?,?,?)"
            " ON CONFLICT(source) DO UPDATE SET watermark=excluded.watermark,"
            " updated_at=excluded.updated_at",
            [source, ts.isoformat(), datetime.now(UTC).isoformat()],
        )
        conn.commit()

    def advance_watermark(self, source: str, candidate: datetime) -> None:
        """Atomically advance watermark for *source* — no-op if *candidate* <= current."""
        conn = self._conn()
        cur = conn.execute(
            "SELECT watermark FROM watermarks WHERE source=?", [source]
        ).fetchone()
        if cur is not None:
            ts = datetime.fromisoformat(cur[0])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if candidate <= ts:
                return
        self.set_watermark(source, candidate)

    def reset_watermark(self, source: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM watermarks WHERE source=?", [source])
        conn.execute("DELETE FROM ingested_hashes WHERE source=?", [source])
        conn.commit()

    def all_watermarks(self) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT w.source, w.watermark, w.updated_at,"
                " COUNT(h.content_hash) AS hash_count"
                " FROM watermarks w"
                " LEFT JOIN ingested_hashes h ON h.source = w.source"
                " GROUP BY w.source, w.watermark, w.updated_at"
                " ORDER BY w.source"
            )
            .fetchall()
        )
        return [
            {"source": r[0], "watermark": r[1], "updated_at": r[2], "hash_count": r[3]}
            for r in rows
        ]

    def is_duplicate(self, source: str, content_hash: str) -> bool:
        row = (
            self._conn()
            .execute(
                "SELECT 1 FROM ingested_hashes WHERE source=? AND content_hash=?",
                [source, content_hash],
            )
            .fetchone()
        )
        return row is not None

    def record_hash(self, source: str, content_hash: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO ingested_hashes(source,content_hash,ingested_at) VALUES(?,?,?)",
            [source, content_hash, datetime.now(UTC).isoformat()],
        )
        conn.commit()

    def hash_count(self, source: str) -> int:
        row = (
            self._conn()
            .execute("SELECT COUNT(*) FROM ingested_hashes WHERE source=?", [source])
            .fetchone()
        )
        return int(row[0]) if row else 0

    # ── Schema contracts ──────────────────────────────────────────────────────

    def get_schema_contract(self, pipeline: str) -> dict[str, Any] | None:
        import json as _json

        row = (
            self._conn()
            .execute(
                "SELECT columns_json, recorded_at FROM schema_contracts WHERE pipeline=?",
                [pipeline],
            )
            .fetchone()
        )
        if row is None:
            return None
        return {"columns": _json.loads(row[0]), "recorded_at": row[1]}

    def set_schema_contract(self, pipeline: str, columns: dict[str, str]) -> None:
        import json as _json

        conn = self._conn()
        conn.execute(
            "INSERT INTO schema_contracts(pipeline,columns_json,recorded_at) VALUES(?,?,?)"
            " ON CONFLICT(pipeline) DO UPDATE SET columns_json=excluded.columns_json,"
            " recorded_at=excluded.recorded_at",
            [pipeline, _json.dumps(columns), datetime.now(UTC).isoformat()],
        )
        conn.commit()

    def record_drift(self, pipeline: str, drift: list[dict[str, Any]]) -> None:
        import json as _json

        conn = self._conn()
        conn.execute(
            "INSERT INTO schema_drift_events(pipeline,drift_json,detected_at) VALUES(?,?,?)",
            [pipeline, _json.dumps(drift), datetime.now(UTC).isoformat()],
        )
        conn.commit()

    def get_drift_events(self, pipeline: str | None = None) -> list[dict[str, Any]]:
        import json as _json

        conn = self._conn()
        if pipeline:
            rows = conn.execute(
                "SELECT id,pipeline,drift_json,detected_at,accepted FROM"
                " schema_drift_events WHERE pipeline=? ORDER BY detected_at DESC",
                [pipeline],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,pipeline,drift_json,detected_at,accepted FROM"
                " schema_drift_events ORDER BY detected_at DESC LIMIT 200"
            ).fetchall()
        return [
            {
                "id": r[0],
                "pipeline": r[1],
                "drift": _json.loads(r[2]),
                "detected_at": r[3],
                "accepted": bool(r[4]),
            }
            for r in rows
        ]

    def accept_drift(self, event_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE schema_drift_events SET accepted=1 WHERE id=?", [event_id])
        conn.commit()

    # ── Compaction runs ───────────────────────────────────────────────────────

    def record_compaction(
        self,
        pipeline: str,
        files_before: int,
        files_after: int,
        bytes_before: int,
        bytes_after: int,
        duration_s: float,
    ) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO compaction_runs(pipeline,files_before,files_after,"
            "bytes_before,bytes_after,duration_s,ran_at) VALUES(?,?,?,?,?,?,?)",
            [
                pipeline,
                files_before,
                files_after,
                bytes_before,
                bytes_after,
                duration_s,
                datetime.now(UTC).isoformat(),
            ],
        )
        conn.commit()

    def get_compaction_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT pipeline,files_before,files_after,bytes_before,bytes_after,"
                "duration_s,ran_at FROM compaction_runs ORDER BY ran_at DESC LIMIT ?",
                [limit],
            )
            .fetchall()
        )
        return [
            {
                "pipeline": r[0],
                "files_before": r[1],
                "files_after": r[2],
                "bytes_before": r[3],
                "bytes_after": r[4],
                "duration_s": round(r[5], 2),
                "ran_at": r[6],
            }
            for r in rows
        ]

    # ── Alert events ──────────────────────────────────────────────────────────

    def record_alert(self, event_type: str, pipeline: str, message: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO alert_events(event_type,pipeline,message,created_at) VALUES(?,?,?,?)",
            [event_type, pipeline, message, datetime.now(UTC).isoformat()],
        )
        conn.commit()
        return cur.lastrowid or 0

    def mark_alert_delivered(self, alert_id: int) -> None:
        conn = self._conn()
        conn.execute("UPDATE alert_events SET delivered=1 WHERE id=?", [alert_id])
        conn.commit()

    def get_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT id,event_type,pipeline,message,delivered,created_at"
                " FROM alert_events ORDER BY created_at DESC LIMIT ?",
                [limit],
            )
            .fetchall()
        )
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "pipeline": r[2],
                "message": r[3],
                "delivered": bool(r[4]),
                "created_at": r[5],
            }
            for r in rows
        ]

    # ── AI traces ─────────────────────────────────────────────────────────────

    def record_trace(
        self,
        agent: str,
        message: str,
        response: str,
        latency_ms: float,
        tool_calls: int = 0,
        status: str = "ok",
        cached: bool = False,
    ) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO ai_traces"
            "(agent,message,response,latency_ms,tool_calls,status,cached,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            [
                agent,
                message[:500],
                response[:2000],
                round(latency_ms, 1),
                tool_calls,
                status,
                1 if cached else 0,
                datetime.now(UTC).isoformat(),
            ],
        )
        conn.commit()
        return cur.lastrowid or 0

    def get_traces(self, agent: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._conn()
        if agent:
            rows = conn.execute(
                "SELECT id,agent,message,response,latency_ms,tool_calls,status,cached,created_at"
                " FROM ai_traces WHERE agent=? ORDER BY created_at DESC LIMIT ?",
                [agent, limit],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,agent,message,response,latency_ms,tool_calls,status,cached,created_at"
                " FROM ai_traces ORDER BY created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        return [
            {
                "id": r[0],
                "agent": r[1],
                "message": r[2],
                "response": r[3],
                "latency_ms": r[4],
                "tool_calls": r[5],
                "status": r[6],
                "cached": bool(r[7]),
                "created_at": r[8],
            }
            for r in rows
        ]

    def prune_traces(self, keep: int = 500) -> int:
        conn = self._conn()
        cur = conn.execute(
            "DELETE FROM ai_traces WHERE id NOT IN"
            " (SELECT id FROM ai_traces ORDER BY created_at DESC LIMIT ?)",
            [keep],
        )
        conn.commit()
        return cur.rowcount

    # ── Quality rules ─────────────────────────────────────────────────────────

    def get_quality_rules(self, pipeline: str) -> list[dict[str, Any]]:
        import json as _json

        rows = (
            self._conn()
            .execute(
                "SELECT id, col_name, rule_type, config, on_failure, enabled FROM quality_rules"
                " WHERE pipeline=? ORDER BY col_name, id",
                (pipeline,),
            )
            .fetchall()
        )
        return [
            {
                "id": r[0],
                "col_name": r[1],
                "rule_type": r[2],
                "config": _json.loads(r[3]),
                "on_failure": r[4],
                "enabled": bool(r[5]),
            }
            for r in rows
        ]

    def add_quality_rule(
        self,
        pipeline: str,
        col_name: str,
        rule_type: str,
        config: dict[str, Any],
        on_failure: str = "warn",
    ) -> int:
        import json as _json

        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO quality_rules"
            " (pipeline, col_name, rule_type, config, on_failure, enabled, created_at)"
            " VALUES (?,?,?,?,?,1,?)",
            (pipeline, col_name, rule_type, _json.dumps(config), on_failure, now),
        )
        conn.commit()
        return int(cur.lastrowid or 0)

    def update_quality_rule(
        self,
        rule_id: int,
        config: dict[str, Any],
        on_failure: str,
        enabled: bool,
    ) -> None:
        import json as _json

        conn = self._conn()
        conn.execute(
            "UPDATE quality_rules SET config=?, on_failure=?, enabled=? WHERE id=?",
            (_json.dumps(config), on_failure, int(enabled), rule_id),
        )
        conn.commit()

    def delete_quality_rule(self, rule_id: int) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM quality_rules WHERE id=?", (rule_id,))
        conn.commit()

    # ── Agent runs + steps ────────────────────────────────────────────────────

    def record_agent_run(self, run: Any) -> None:
        import json as _json

        conn = self._conn()
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO agent_runs"
            " (run_id, agent_name, user_message, final_answer, tool_calls,"
            "  total_latency_ms, status, mode, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(run_id) DO UPDATE SET"
            "  final_answer=excluded.final_answer, tool_calls=excluded.tool_calls,"
            "  total_latency_ms=excluded.total_latency_ms, status=excluded.status",
            [
                run.run_id,
                run.agent_name,
                run.user_message[:500],
                run.final_answer[:2000],
                run.tool_calls,
                round(run.total_latency_ms, 1),
                run.status,
                getattr(run, "mode", "ask"),
                now,
            ],
        )
        for step in getattr(run, "steps", []):
            conn.execute(
                "INSERT OR IGNORE INTO agent_steps"
                " (run_id, step_id, step_type, tool_name, inputs_json, output_preview,"
                "  status, duration_ms, tokens)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    run.run_id,
                    step.step_id,
                    step.type,
                    step.tool_name,
                    _json.dumps(step.inputs),
                    step.output_preview[:500],
                    step.status,
                    round(step.duration_ms, 1) if step.duration_ms is not None else None,
                    step.tokens,
                ],
            )
        conn.commit()

    def get_agent_runs(self, limit: int = 100, agent: str = "") -> list[dict[str, Any]]:
        q = "SELECT * FROM agent_runs"
        params: list[Any] = []
        if agent:
            q += " WHERE agent_name=?"
            params.append(agent)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn().execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def get_agent_steps(self, run_id: str) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute(
                "SELECT * FROM agent_steps WHERE run_id=? ORDER BY step_id",
                [run_id],
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_run_stats(self) -> dict[str, Any]:
        conn = self._conn()
        total = (conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone() or [0])[0]
        errors = (
            conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='error'").fetchone() or [0]
        )[0]
        avg_lat = (
            conn.execute("SELECT AVG(total_latency_ms) FROM agent_runs").fetchone() or [None]
        )[0]
        tool_calls = (conn.execute("SELECT SUM(tool_calls) FROM agent_runs").fetchone() or [0])[0]
        return {
            "total_runs": int(total),
            "error_count": int(errors),
            "avg_latency_ms": round(avg_lat, 1) if avg_lat else 0,
            "total_tool_calls": int(tool_calls or 0),
        }

    # ── Embedding collections ─────────────────────────────────────────────────

    def upsert_embedding_collection(
        self,
        name: str,
        source_table: str,
        source_column: str,
        model: str,
        vector_count: int,
        dim: int = 0,
        duration_s: float | None = None,
        status: str = "ok",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        conn.execute(
            "INSERT INTO embedding_collections"
            " (name, source_table, source_column, model,"
            "  vector_count, dim, duration_s, status, built_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET"
            "  source_table=excluded.source_table, source_column=excluded.source_column,"
            "  model=excluded.model, vector_count=excluded.vector_count,"
            "  dim=excluded.dim, duration_s=excluded.duration_s,"
            "  status=excluded.status, built_at=excluded.built_at, updated_at=excluded.updated_at",
            [name, source_table, source_column, model, vector_count,
             dim, duration_s, status, now, now],
        )
        conn.commit()

    def get_embedding_collections(self) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute("SELECT * FROM embedding_collections ORDER BY updated_at DESC")
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ── Embedding vectors ─────────────────────────────────────────────────────

    def store_vectors(
        self,
        collection_name: str,
        rows: list[tuple[int, str, list[float]]],
    ) -> None:
        """Replace all vectors for a collection. Each row is (row_id, text, embedding)."""
        import json as _json

        conn = self._conn()
        conn.execute("DELETE FROM embedding_vectors WHERE collection_name=?", [collection_name])
        conn.executemany(
            "INSERT INTO embedding_vectors(collection_name, row_id, source_text, embedding_json)"
            " VALUES(?,?,?,?)",
            [(collection_name, r[0], r[1], _json.dumps(r[2])) for r in rows],
        )
        conn.commit()

    def get_vectors(
        self, collection_name: str
    ) -> list[dict[str, Any]]:
        import json as _json

        rows = (
            self._conn()
            .execute(
                "SELECT row_id, source_text, embedding_json"
                " FROM embedding_vectors WHERE collection_name=? ORDER BY row_id",
                [collection_name],
            )
            .fetchall()
        )
        return [
            {"row_id": r[0], "source_text": r[1], "embedding": _json.loads(r[2])}
            for r in rows
        ]


    # ── Quality tests (Phase 5) ─────────────────────────────────────────────

    def add_quality_test(
        self, table_name: str, test_type: str, col_name: str = "", threshold: str = "",
    ) -> int:
        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO quality_tests(table_name, test_type, col_name, threshold, created_at)"
            " VALUES(?,?,?,?,?)",
            [table_name, test_type, col_name, threshold, now],
        )
        conn.commit()
        return cur.lastrowid or 0

    def get_quality_tests(self) -> list[dict[str, Any]]:
        return [
            dict(r) for r in self._conn()
            .execute("SELECT * FROM quality_tests ORDER BY created_at DESC")
            .fetchall()
        ]

    # ── Model registry (Phase 5) ────────────────────────────────────────────

    def add_model_registry_entry(
        self, model_name: str, artifact_path: str, stage: str = "development",
        algorithm: str = "", feature_names: list[str] | None = None,
        target: str = "",
    ) -> int:
        import json as _json

        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO model_registry_entries"
            " (model_name, artifact_path, stage, algorithm, feature_names, target, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            [model_name, artifact_path, stage, algorithm,
             _json.dumps(feature_names or []), target, now],
        )
        conn.commit()
        return cur.lastrowid or 0

    def get_model_registry(self) -> list[dict[str, Any]]:
        import json as _json

        rows = (
            self._conn()
            .execute(
                "SELECT * FROM model_registry_entries ORDER BY model_name, created_at DESC"
            )
            .fetchall()
        )
        return [
            {k: _json.loads(v) if k == "feature_names" else v for k, v in dict(r).items()}
            for r in rows
        ]

    # ── Scheduler leader election (Phase 2, SQLite always True) ──────────────

    def try_scheduler_leadership(self) -> bool:
        return True

    def release_scheduler_leadership(self) -> None:
        pass

# ── PostgreSQL schema ──────────────────────────────────────────────────────────

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_state (
    pipeline    TEXT PRIMARY KEY,
    last_run_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_locks (
    pipeline   TEXT PRIMARY KEY,
    locked_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watermarks (
    source      TEXT PRIMARY KEY,
    watermark   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingested_hashes (
    source       TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    ingested_at  TEXT NOT NULL,
    PRIMARY KEY (source, content_hash)
);

CREATE TABLE IF NOT EXISTS schema_contracts (
    pipeline     TEXT PRIMARY KEY,
    columns_json TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_drift_events (
    id          BIGSERIAL PRIMARY KEY,
    pipeline    TEXT NOT NULL,
    drift_json  TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    accepted    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS compaction_runs (
    id            BIGSERIAL PRIMARY KEY,
    pipeline      TEXT NOT NULL,
    files_before  INTEGER NOT NULL DEFAULT 0,
    files_after   INTEGER NOT NULL DEFAULT 0,
    bytes_before  INTEGER NOT NULL DEFAULT 0,
    bytes_after   INTEGER NOT NULL DEFAULT 0,
    duration_s    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    ran_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
    id          BIGSERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,
    pipeline    TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT '',
    delivered   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letter_runs (
    id          BIGSERIAL PRIMARY KEY,
    pipeline    TEXT NOT NULL,
    error       TEXT NOT NULL DEFAULT '',
    attempts    INTEGER NOT NULL DEFAULT 1,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run_state (
    pipeline      TEXT PRIMARY KEY,
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    state         TEXT NOT NULL DEFAULT 'idle'
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           BIGSERIAL PRIMARY KEY,
    pipeline     TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    error        TEXT,
    triggered_by TEXT NOT NULL DEFAULT 'scheduler',
    duration_s   DOUBLE PRECISION,
    request_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline
    ON pipeline_runs(pipeline, started_at DESC);

CREATE TABLE IF NOT EXISTS ai_traces (
    id           BIGSERIAL PRIMARY KEY,
    agent        TEXT NOT NULL,
    message      TEXT NOT NULL DEFAULT '',
    response     TEXT NOT NULL DEFAULT '',
    latency_ms   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    tool_calls   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'ok',
    cached       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_traces_created
    ON ai_traces(created_at DESC);

CREATE TABLE IF NOT EXISTS quality_rules (
    id          BIGSERIAL PRIMARY KEY,
    pipeline    TEXT NOT NULL,
    col_name    TEXT NOT NULL,
    rule_type   TEXT NOT NULL,
    config      TEXT NOT NULL DEFAULT '{}',
    on_failure  TEXT NOT NULL DEFAULT 'warn',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qr_pipeline ON quality_rules(pipeline);

CREATE TABLE IF NOT EXISTS agent_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL UNIQUE,
    agent_name      TEXT NOT NULL,
    user_message    TEXT NOT NULL DEFAULT '',
    final_answer    TEXT NOT NULL DEFAULT '',
    tool_calls      INTEGER NOT NULL DEFAULT 0,
    total_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'done',
    mode            TEXT NOT NULL DEFAULT 'ask',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS agent_steps (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES agent_runs(run_id),
    step_id         INTEGER NOT NULL,
    step_type       TEXT NOT NULL,
    tool_name       TEXT,
    inputs_json     TEXT NOT NULL DEFAULT '{}',
    output_preview  TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'done',
    duration_ms     DOUBLE PRECISION,
    tokens          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id, step_id);

CREATE TABLE IF NOT EXISTS embedding_collections (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    source_table    TEXT NOT NULL DEFAULT '',
    source_column   TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    vector_count    INTEGER NOT NULL DEFAULT 0,
    dim             INTEGER NOT NULL DEFAULT 0,
    duration_s      DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'pending',
    built_at        TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_vectors (
    id              BIGSERIAL PRIMARY KEY,
    collection_name TEXT NOT NULL,
    row_id          INTEGER NOT NULL,
    source_text     TEXT NOT NULL,
    embedding_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_collection
    ON embedding_vectors(collection_name);

CREATE TABLE IF NOT EXISTS quality_tests (
    id          BIGSERIAL PRIMARY KEY,
    table_name  TEXT NOT NULL,
    test_type   TEXT NOT NULL,
    col_name    TEXT NOT NULL DEFAULT '',
    threshold   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry_entries (
    id              BIGSERIAL PRIMARY KEY,
    model_name      TEXT NOT NULL,
    artifact_path   TEXT NOT NULL,
    stage           TEXT NOT NULL DEFAULT 'development',
    algorithm       TEXT NOT NULL DEFAULT '',
    feature_names   TEXT NOT NULL DEFAULT '[]',
    target          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mre_model ON model_registry_entries(model_name, created_at DESC);
"""


# ── PostgreSQL backend ────────────────────────────────────────────────────────


class PgStudioDb:
    """PostgreSQL-backed store mirroring StudioDb's interface.

    Uses a SQLAlchemy engine (connection pool) so every method gets a fresh
    connection from the pool. Pipeline locks use ``pg_advisory_lock`` for
    cross-pod mutual exclusion. Scheduler leadership uses the same mechanism.
    """

    def __init__(self, dsn: str) -> None:
        from sqlalchemy import create_engine

        self._engine = create_engine(dsn, pool_size=4, max_overflow=8)
        self._held_locks: dict[str, Any] = {}
        self._leader_conn: Any = None
        self._init_schema()

    def _conn(self) -> Any:
        from sqlalchemy import text

        conn = self._engine.connect()
        conn.execute(text("SET TIME ZONE 'UTC'"))
        return conn

    def _init_schema(self) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            for stmt in _PG_SCHEMA.split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))
            conn.commit()

    # ── Scheduler state ─────────────────────────────────────────────────────

    def get_last_run(self, pipeline: str) -> datetime | None:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT last_run_at FROM scheduler_state WHERE pipeline=:p"), {"p": pipeline}
            ).fetchone()
        if row is None:
            return None
        ts = datetime.fromisoformat(row[0])
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

    def set_last_run(self, pipeline: str, ts: datetime) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO scheduler_state(pipeline,last_run_at) VALUES(:p,:t)"
                     " ON CONFLICT(pipeline) DO UPDATE SET last_run_at=excluded.last_run_at"),
                {"p": pipeline, "t": ts.isoformat()},
            )
            conn.commit()

    # ── Run locking (advisory locks for cross-pod safety) ────────────────────
    # ponytail: each lock holds its own PG connection because advisory locks
    # are session-scoped — releasing on a different pool connection is a no-op.
    # Dict lifecycle: acquire_lock() stores conn, release_lock() pops & closes.

    def acquire_lock(self, pipeline: str) -> bool:
        from sqlalchemy import text

        key = _lock_key(pipeline)
        conn = self._engine.connect()
        conn.execute(text("SET TIME ZONE 'UTC'"))
        try:
            locked = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar()
            if locked:
                conn.execute(
                    text("INSERT INTO pipeline_locks(pipeline,locked_at) VALUES(:p,:t)"
                         " ON CONFLICT(pipeline) DO UPDATE SET locked_at=excluded.locked_at"),
                    {"p": pipeline, "t": datetime.now(UTC).isoformat()},
                )
                conn.commit()
                self._held_locks[pipeline] = conn
                return True
            conn.close()
            return False
        except Exception:
            conn.close()
            raise

    def release_lock(self, pipeline: str) -> None:
        from sqlalchemy import text

        conn = self._held_locks.pop(pipeline, None)
        if conn is None:
            return
        try:
            key = _lock_key(pipeline)
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            conn.execute(text("DELETE FROM pipeline_locks WHERE pipeline=:p"), {"p": pipeline})
            conn.commit()
        finally:
            conn.close()

    def clear_stale_locks(self, timeout_s: int = 7200) -> int:
        from sqlalchemy import text

        cutoff_iso = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() - timeout_s, tz=UTC
        ).isoformat()
        with self._conn() as conn:
            result = conn.execute(
                text("DELETE FROM pipeline_locks WHERE locked_at < :c"), {"c": cutoff_iso}
            )
            conn.commit()
            return result.rowcount  # type: ignore[no-any-return]

    def locked_pipelines(self) -> list[str]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(text("SELECT pipeline FROM pipeline_locks")).fetchall()
        return [r[0] for r in rows]

    # ── Persistent retry state ───────────────────────────────────────────────

    def get_run_state(self, pipeline: str) -> dict[str, Any]:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT attempts, next_retry_at, state"
                     " FROM pipeline_run_state WHERE pipeline=:p"),
                {"p": pipeline},
            ).fetchone()
        if row is None:
            return {"attempts": 0, "next_retry_at": None, "state": "idle"}
        return {"attempts": row[0], "next_retry_at": row[1], "state": row[2]}

    def increment_attempts(self, pipeline: str, next_retry_at: datetime) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO pipeline_run_state(pipeline, attempts, next_retry_at, state)"
                     " VALUES(:p, 1, :n, 'retrying')"
                     " ON CONFLICT(pipeline) DO UPDATE SET"
                     "   attempts = pipeline_run_state.attempts + 1,"
                     "   next_retry_at = :n, state = 'retrying'"),
                {"p": pipeline, "n": next_retry_at.isoformat()},
            )
            conn.commit()
            row = conn.execute(
                text("SELECT attempts FROM pipeline_run_state WHERE pipeline=:p"), {"p": pipeline}
            ).fetchone()
        return row[0] if row else 1

    def mark_dead(self, pipeline: str) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO pipeline_run_state(pipeline, attempts, next_retry_at, state)"
                     " VALUES(:p, 0, NULL, 'dead')"
                     " ON CONFLICT(pipeline) DO UPDATE SET"
                     "   next_retry_at = NULL, state = 'dead'"),
                {"p": pipeline},
            )
            conn.commit()

    def clear_run_state(self, pipeline: str) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(text("DELETE FROM pipeline_run_state WHERE pipeline=:p"), {"p": pipeline})
            conn.commit()

    def all_retry_states(self) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT pipeline, attempts, next_retry_at, state"
                     " FROM pipeline_run_state WHERE state != 'idle'")
            ).fetchall()
        return [
            {"pipeline": r[0], "attempts": r[1], "next_retry_at": r[2], "state": r[3]}
            for r in rows
        ]

    # ── Pipeline run history ─────────────────────────────────────────────────

    def start_run(
        self, pipeline: str, triggered_by: str = "scheduler", request_id: str = "",
    ) -> int:
        from sqlalchemy import text

        sql = ("INSERT INTO pipeline_runs(pipeline, started_at, status, triggered_by, request_id)"
               " VALUES(:p, :t, 'running', :tr, :r) RETURNING id")
        with self._conn() as conn:
            row = conn.execute(
                text(sql),
                {"p": pipeline, "t": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f"),
                 "tr": triggered_by, "r": request_id or ""},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def finish_run(self, run_id: int, status: str, error: str = "") -> None:
        from sqlalchemy import text

        finished = datetime.now(UTC)
        with self._conn() as conn:
            row = conn.execute(
                text("SELECT started_at FROM pipeline_runs WHERE id=:id"), {"id": run_id}
            ).fetchone()
            started = (
                datetime.fromisoformat(row[0]).replace(tzinfo=UTC)  # type: ignore[union-attr]
                if row else None
            )
            duration_s = (
                round((finished - started).total_seconds(), 2)
                if started else None
            )
            conn.execute(
                text("UPDATE pipeline_runs SET finished_at=:f, status=:s, error=:e, duration_s=:d"
                     " WHERE id=:id"),
                {"f": finished.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                 "s": status, "e": error or "", "d": duration_s, "id": run_id},
            )
            conn.commit()

    def get_runs(self, pipeline: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            if pipeline:
                rows = conn.execute(
                    text("SELECT id,pipeline,started_at,finished_at,status,error,"
                         "triggered_by,duration_s,request_id"
                         " FROM pipeline_runs WHERE pipeline=:p"
                         " ORDER BY started_at DESC LIMIT :lim"),
                    {"p": pipeline, "lim": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT id,pipeline,started_at,finished_at,status,error,"
                         "triggered_by,duration_s,request_id"
                         " FROM pipeline_runs ORDER BY started_at DESC LIMIT :lim"),
                    {"lim": limit},
                ).fetchall()
        return [
            {
                "id": r[0], "pipeline": r[1], "started_at": r[2],
                "finished_at": r[3], "status": r[4], "error": r[5] or "",
                "triggered_by": r[6],
                "duration_s": round(r[7], 2) if r[7] is not None else None,
                "request_id": r[8] or "",
            }
            for r in rows
        ]

    def prune_runs(self, keep: int = 1000) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            result = conn.execute(
                text("DELETE FROM pipeline_runs WHERE id NOT IN"
                     " (SELECT id FROM pipeline_runs ORDER BY started_at DESC LIMIT :k)"),
                {"k": keep},
            )
            conn.commit()
        return result.rowcount  # type: ignore[no-any-return]

    # ── Dead letter ──────────────────────────────────────────────────────────

    def record_dead_letter(self, pipeline: str, error: str, attempts: int) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(text("DELETE FROM dead_letter_runs WHERE pipeline=:p"), {"p": pipeline})
            conn.execute(
                text("INSERT INTO dead_letter_runs(pipeline,error,attempts,recorded_at)"
                     " VALUES(:p,:e,:a,:r)"),
                {"p": pipeline, "e": error, "a": attempts,
                 "r": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def get_dead_letter(self) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT pipeline,error,attempts,recorded_at"
                     " FROM dead_letter_runs ORDER BY recorded_at DESC")
            ).fetchall()
        return [
            {"pipeline": r[0], "error": r[1], "attempts": r[2], "recorded_at": r[3]}
            for r in rows
        ]

    def clear_dead_letter(self, pipeline: str) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(text("DELETE FROM dead_letter_runs WHERE pipeline=:p"), {"p": pipeline})
            conn.commit()

    # ── Pause state ──────────────────────────────────────────────────────────

    def is_paused(self) -> bool:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT value FROM scheduler_settings WHERE key='paused'")
            ).fetchone()
        return row is not None and row[0] == "1"

    def set_paused(self, paused: bool) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO scheduler_settings(key,value) VALUES('paused',:v)"
                     " ON CONFLICT(key) DO UPDATE SET value=excluded.value"),
                {"v": "1" if paused else "0"},
            )
            conn.commit()

    # ── Watermarks ───────────────────────────────────────────────────────────

    def get_watermark(self, source: str) -> datetime | None:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT watermark FROM watermarks WHERE source=:s"), {"s": source}
            ).fetchone()
        if row is None:
            return None
        ts = datetime.fromisoformat(row[0])
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

    def set_watermark(self, source: str, ts: datetime) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO watermarks(source,watermark,updated_at) VALUES(:s,:w,:u)"
                     " ON CONFLICT(source) DO UPDATE SET"
                     " watermark=excluded.watermark, updated_at=excluded.updated_at"),
                {"s": source, "w": ts.isoformat(), "u": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def advance_watermark(self, source: str, candidate: datetime) -> None:
        """Atomically advance watermark — no-op if *candidate* <= current."""
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO watermarks(source,watermark,updated_at) VALUES(:s,:w,:u)"
                     " ON CONFLICT(source) DO UPDATE SET"
                     " watermark=:w, updated_at=:u"
                     " WHERE watermarks.watermark < :w"),
                {"s": source, "w": candidate.isoformat(), "u": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def reset_watermark(self, source: str) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(text("DELETE FROM watermarks WHERE source=:s"), {"s": source})
            conn.execute(text("DELETE FROM ingested_hashes WHERE source=:s"), {"s": source})
            conn.commit()

    def all_watermarks(self) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT w.source, w.watermark, w.updated_at,"
                     " COUNT(h.content_hash) AS hash_count"
                     " FROM watermarks w"
                     " LEFT JOIN ingested_hashes h ON h.source = w.source"
                     " GROUP BY w.source, w.watermark, w.updated_at"
                     " ORDER BY w.source")
            ).fetchall()
        return [
            {"source": r[0], "watermark": r[1], "updated_at": r[2], "hash_count": r[3]}
            for r in rows
        ]

    def is_duplicate(self, source: str, content_hash: str) -> bool:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT 1 FROM ingested_hashes"
                     " WHERE source=:s AND content_hash=:h"),
                {"s": source, "h": content_hash},
            ).fetchone()
        return row is not None

    def record_hash(self, source: str, content_hash: str) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO ingested_hashes(source,content_hash,ingested_at)"
                     " VALUES(:s,:h,:t) ON CONFLICT DO NOTHING"),
                {"s": source, "h": content_hash, "t": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def hash_count(self, source: str) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM ingested_hashes WHERE source=:s"), {"s": source}
            ).fetchone()
        return int(row[0]) if row else 0

    # ── Schema contracts ─────────────────────────────────────────────────────

    def get_schema_contract(self, pipeline: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("SELECT columns_json, recorded_at FROM schema_contracts WHERE pipeline=:p"),
                {"p": pipeline},
            ).fetchone()
        if row is None:
            return None
        import json as _json

        return {"columns": _json.loads(row[0]), "recorded_at": row[1]}

    def set_schema_contract(self, pipeline: str, columns: dict[str, str]) -> None:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO schema_contracts(pipeline,columns_json,recorded_at)"
                     " VALUES(:p,:c,:r)"
                     " ON CONFLICT(pipeline) DO UPDATE SET"
                     " columns_json=excluded.columns_json, recorded_at=excluded.recorded_at"),
                {"p": pipeline, "c": _json.dumps(columns),
                 "r": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def record_drift(self, pipeline: str, drift: list[dict[str, Any]]) -> None:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO schema_drift_events(pipeline,drift_json,detected_at)"
                     " VALUES(:p,:d,:t)"),
                {"p": pipeline, "d": _json.dumps(drift),
                 "t": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def get_drift_events(self, pipeline: str | None = None) -> list[dict[str, Any]]:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            if pipeline:
                rows = conn.execute(
                    text("SELECT id,pipeline,drift_json,detected_at,accepted"
                         " FROM schema_drift_events WHERE pipeline=:p"
                         " ORDER BY detected_at DESC"),
                    {"p": pipeline},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT id,pipeline,drift_json,detected_at,accepted"
                         " FROM schema_drift_events ORDER BY detected_at DESC LIMIT 200")
                ).fetchall()
        return [
            {"id": r[0], "pipeline": r[1], "drift": _json.loads(r[2]),
             "detected_at": r[3], "accepted": bool(r[4])}
            for r in rows
        ]

    def accept_drift(self, event_id: int) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("UPDATE schema_drift_events SET accepted=1 WHERE id=:id"), {"id": event_id}
            )
            conn.commit()

    # ── Compaction runs ──────────────────────────────────────────────────────

    def record_compaction(
        self, pipeline: str, files_before: int, files_after: int,
        bytes_before: int, bytes_after: int, duration_s: float,
    ) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO compaction_runs"
                     "(pipeline,files_before,files_after,bytes_before,bytes_after,duration_s,ran_at)"
                     " VALUES(:p,:fb,:fa,:bb,:ba,:d,:r)"),
                {"p": pipeline, "fb": files_before, "fa": files_after,
                 "bb": bytes_before, "ba": bytes_after, "d": duration_s,
                 "r": datetime.now(UTC).isoformat()},
            )
            conn.commit()

    def get_compaction_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT pipeline,files_before,files_after,bytes_before,bytes_after,"
                     "duration_s,ran_at FROM compaction_runs ORDER BY ran_at DESC LIMIT :lim"),
                {"lim": limit},
            ).fetchall()
        return [
            {"pipeline": r[0], "files_before": r[1], "files_after": r[2],
             "bytes_before": r[3], "bytes_after": r[4],
             "duration_s": round(r[5], 2), "ran_at": r[6]}
            for r in rows
        ]

    # ── Alert events ─────────────────────────────────────────────────────────

    def record_alert(self, event_type: str, pipeline: str, message: str) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("INSERT INTO alert_events(event_type,pipeline,message,created_at)"
                     " VALUES(:e,:p,:m,:t) RETURNING id"),
                {"e": event_type, "p": pipeline, "m": message,
                 "t": datetime.now(UTC).isoformat()},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def mark_alert_delivered(self, alert_id: int) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("UPDATE alert_events SET delivered=1 WHERE id=:id"), {"id": alert_id}
            )
            conn.commit()

    def get_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT id,event_type,pipeline,message,delivered,created_at"
                     " FROM alert_events ORDER BY created_at DESC LIMIT :lim"),
                {"lim": limit},
            ).fetchall()
        return [
            {"id": r[0], "event_type": r[1], "pipeline": r[2], "message": r[3],
             "delivered": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]

    # ── AI traces ────────────────────────────────────────────────────────────

    def record_trace(
        self, agent: str, message: str, response: str, latency_ms: float,
        tool_calls: int = 0, status: str = "ok", cached: bool = False,
    ) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            row = conn.execute(
                text("INSERT INTO ai_traces"
                     "(agent,message,response,latency_ms,tool_calls,status,cached,created_at)"
                     " VALUES(:a,:m,:r,:l,:tc,:s,:c,:t) RETURNING id"),
                {"a": agent, "m": message[:500], "r": response[:2000],
                 "l": round(latency_ms, 1), "tc": tool_calls, "s": status,
                 "c": 1 if cached else 0, "t": datetime.now(UTC).isoformat()},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def get_traces(self, agent: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        from sqlalchemy import text

        cols = ("SELECT id,agent,message,response,latency_ms,"
                "tool_calls,status,cached,created_at")
        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    text(f"{cols} FROM ai_traces WHERE agent=:a"
                         " ORDER BY created_at DESC LIMIT :lim"),
                    {"a": agent, "lim": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(f"{cols} FROM ai_traces ORDER BY created_at DESC LIMIT :lim"),
                    {"lim": limit},
                ).fetchall()
        return [
            {"id": r[0], "agent": r[1], "message": r[2], "response": r[3],
             "latency_ms": r[4], "tool_calls": r[5], "status": r[6],
             "cached": bool(r[7]), "created_at": r[8]}
            for r in rows
        ]

    def prune_traces(self, keep: int = 500) -> int:
        from sqlalchemy import text

        with self._conn() as conn:
            result = conn.execute(
                text("DELETE FROM ai_traces WHERE id NOT IN"
                     " (SELECT id FROM ai_traces ORDER BY created_at DESC LIMIT :k)"),
                {"k": keep},
            )
            conn.commit()
        return result.rowcount  # type: ignore[no-any-return]

    # ── Quality rules ────────────────────────────────────────────────────────

    def get_quality_rules(self, pipeline: str) -> list[dict[str, Any]]:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT id, col_name, rule_type, config, on_failure, enabled"
                     " FROM quality_rules WHERE pipeline=:p ORDER BY col_name, id"),
                {"p": pipeline},
            ).fetchall()
        return [
            {"id": r[0], "col_name": r[1], "rule_type": r[2],
             "config": _json.loads(r[3]), "on_failure": r[4], "enabled": bool(r[5])}
            for r in rows
        ]

    def add_quality_rule(
        self, pipeline: str, col_name: str, rule_type: str,
        config: dict[str, Any], on_failure: str = "warn",
    ) -> int:
        import json as _json

        from sqlalchemy import text

        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                text("INSERT INTO quality_rules"
                     "(pipeline, col_name, rule_type, config, on_failure, enabled, created_at)"
                     " VALUES(:p,:c,:r,:cfg,:of,1,:t) RETURNING id"),
                {"p": pipeline, "c": col_name, "r": rule_type,
                 "cfg": _json.dumps(config), "of": on_failure, "t": now},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def update_quality_rule(
        self, rule_id: int, config: dict[str, Any], on_failure: str, enabled: bool,
    ) -> None:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("UPDATE quality_rules SET config=:c, on_failure=:of, enabled=:e WHERE id=:id"),
                {"c": _json.dumps(config), "of": on_failure, "e": int(enabled), "id": rule_id},
            )
            conn.commit()

    def delete_quality_rule(self, rule_id: int) -> None:
        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(text("DELETE FROM quality_rules WHERE id=:id"), {"id": rule_id})
            conn.commit()

    # ── Agent runs + steps ───────────────────────────────────────────────────

    def record_agent_run(self, run: Any) -> None:
        import json as _json

        from sqlalchemy import text

        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO agent_runs"
                     "(run_id, agent_name, user_message, final_answer, tool_calls,"
                     " total_latency_ms, status, mode, created_at)"
                     " VALUES(:rid,:an,:um,:fa,:tc,:tlm,:s,:m,:t)"
                     " ON CONFLICT(run_id) DO UPDATE SET"
                     "  final_answer=excluded.final_answer, tool_calls=excluded.tool_calls,"
                     "  total_latency_ms=excluded.total_latency_ms, status=excluded.status"),
                {"rid": run.run_id, "an": run.agent_name,
                 "um": run.user_message[:500], "fa": run.final_answer[:2000],
                 "tc": run.tool_calls, "tlm": round(run.total_latency_ms, 1),
                 "s": run.status, "m": getattr(run, "mode", "ask"), "t": now},
            )
            for step in getattr(run, "steps", []):
                conn.execute(
                    text("INSERT INTO agent_steps"
                         "(run_id, step_id, step_type, tool_name, inputs_json, output_preview,"
                         " status, duration_ms, tokens)"
                         " VALUES(:rid,:si,:st,:tn,:ij,:op,:s,:dm,:tk)"
                         " ON CONFLICT DO NOTHING"),
                    {"rid": run.run_id, "si": step.step_id, "st": step.type,
                     "tn": step.tool_name, "ij": _json.dumps(step.inputs),
                     "op": step.output_preview[:500], "s": step.status,
                     "dm": round(step.duration_ms, 1) if step.duration_ms is not None else None,
                     "tk": step.tokens},
                )
            conn.commit()

    def get_agent_runs(self, limit: int = 100, agent: str = "") -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    text("SELECT * FROM agent_runs WHERE agent_name=:a"
                         " ORDER BY created_at DESC LIMIT :lim"),
                    {"a": agent, "lim": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT :lim"),
                    {"lim": limit},
                ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_agent_steps(self, run_id: str) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM agent_steps WHERE run_id=:rid ORDER BY step_id"),
                {"rid": run_id},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_run_stats(self) -> dict[str, Any]:
        from sqlalchemy import text

        with self._conn() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM agent_runs")).scalar() or 0
            errors = conn.execute(
                text("SELECT COUNT(*) FROM agent_runs WHERE status='error'")
            ).scalar() or 0
            avg_lat = conn.execute(
                text("SELECT AVG(total_latency_ms) FROM agent_runs")
            ).scalar()
            tool_calls = conn.execute(
                text("SELECT SUM(tool_calls) FROM agent_runs")
            ).scalar() or 0
        return {
            "total_runs": int(total),
            "error_count": int(errors),
            "avg_latency_ms": round(avg_lat, 1) if avg_lat else 0,
            "total_tool_calls": int(tool_calls),
        }

    # ── Embedding collections ────────────────────────────────────────────────

    def upsert_embedding_collection(
        self, name: str, source_table: str, source_column: str, model: str,
        vector_count: int, dim: int = 0, duration_s: float | None = None,
        status: str = "ok",
    ) -> None:
        from sqlalchemy import text

        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            sql = ("INSERT INTO embedding_collections"
                   "(name, source_table, source_column, model,"
                   " vector_count, dim, duration_s, status, built_at, updated_at)"
                   " VALUES(:n,:st,:sc,:m,:vc,:dim,:dur,:s,:ba,:ua)"
                   " ON CONFLICT(name) DO UPDATE SET"
                   "  source_table=excluded.source_table,"
                   "  source_column=excluded.source_column,"
                   "  model=excluded.model,"
                   "  vector_count=excluded.vector_count,"
                   "  dim=excluded.dim, duration_s=excluded.duration_s,"
                   "  status=excluded.status, built_at=excluded.built_at,"
                   "  updated_at=excluded.updated_at")
            conn.execute(
                text(sql),
                {"n": name, "st": source_table, "sc": source_column, "m": model,
                 "vc": vector_count, "dim": dim, "dur": duration_s, "s": status,
                 "ba": now, "ua": now},
            )
            conn.commit()

    def get_embedding_collections(self) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM embedding_collections ORDER BY updated_at DESC")
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    # ── Embedding vectors ────────────────────────────────────────────────────

    def store_vectors(
        self, collection_name: str, rows: list[tuple[int, str, list[float]]],
    ) -> None:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            conn.execute(
                text("DELETE FROM embedding_vectors WHERE collection_name=:c"),
                {"c": collection_name},
            )
            for row_id, source_text, embedding in rows:
                conn.execute(
                    text("INSERT INTO embedding_vectors"
                         "(collection_name, row_id, source_text, embedding_json)"
                         " VALUES(:c,:r,:s,:e)"),
                    {"c": collection_name, "r": row_id, "s": source_text,
                     "e": _json.dumps(embedding)},
                )
            conn.commit()

    def get_vectors(self, collection_name: str) -> list[dict[str, Any]]:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT row_id, source_text, embedding_json"
                     " FROM embedding_vectors WHERE collection_name=:c ORDER BY row_id"),
                {"c": collection_name},
            ).fetchall()
        return [
            {"row_id": r[0], "source_text": r[1], "embedding": _json.loads(r[2])}
            for r in rows
        ]

    # ── Quality tests (Phase 5) ─────────────────────────────────────────────

    def add_quality_test(
        self, table_name: str, test_type: str, col_name: str = "", threshold: str = "",
    ) -> int:
        from sqlalchemy import text

        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                text("INSERT INTO quality_tests(table_name,test_type,col_name,threshold,created_at)"
                     " VALUES(:tn,:tt,:cn,:th,:t) RETURNING id"),
                {"tn": table_name, "tt": test_type, "cn": col_name, "th": threshold, "t": now},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def get_quality_tests(self) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM quality_tests ORDER BY created_at DESC")
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    # ── Model registry (Phase 5) ────────────────────────────────────────────

    def add_model_registry_entry(
        self, model_name: str, artifact_path: str, stage: str = "development",
        algorithm: str = "", feature_names: list[str] | None = None, target: str = "",
    ) -> int:
        import json as _json

        from sqlalchemy import text

        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            sql = ("INSERT INTO model_registry_entries"
                   "(model_name, artifact_path, stage, algorithm,"
                   " feature_names, target, created_at)"
                   " VALUES(:mn,:ap,:st,:al,:fn,:tg,:t) RETURNING id")
            row = conn.execute(
                text(sql),
                {"mn": model_name, "ap": artifact_path, "st": stage, "al": algorithm,
                 "fn": _json.dumps(feature_names or []), "tg": target, "t": now},
            ).fetchone()
            conn.commit()
        return row[0] if row else 0

    def get_model_registry(self) -> list[dict[str, Any]]:
        import json as _json

        from sqlalchemy import text

        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM model_registry_entries ORDER BY model_name, created_at DESC")
            ).fetchall()
        return [
            {k: _json.loads(v) if k == "feature_names" else v for k, v in dict(r._mapping).items()}
            for r in rows
        ]

    # ── Scheduler leader election (Phase 2) ──────────────────────────────────
    # ponytail: same session-scoped lock issue as pipeline locks — keep conn.

    def try_scheduler_leadership(self) -> bool:
        from sqlalchemy import text

        key = _lock_key("dex-studio-scheduler-leader")
        conn = self._engine.connect()
        conn.execute(text("SET TIME ZONE 'UTC'"))
        try:
            locked = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar()
            conn.commit()
            if locked:
                self._leader_conn = conn
                return True
            conn.close()
            return False
        except Exception:
            conn.close()
            raise

    def release_scheduler_leadership(self) -> None:
        from sqlalchemy import text

        conn, self._leader_conn = self._leader_conn, None
        if conn is None:
            return
        try:
            key = _lock_key("dex-studio-scheduler-leader")
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            conn.commit()
        finally:
            conn.close()


# ── Process-level singleton accessor ─────────────────────────────────────────

_GLOBAL_DB: StudioDb | PgStudioDb | None = None
_GLOBAL_DB_PATH: Path | None = None


def _resolve_sqlite_path(eng: Any) -> Path | None:
    """Extract the studio.db path from the engine's project directory."""
    try:
        db_dir = Path(str(getattr(eng, "_dex_dir", None) or getattr(eng, "config_path", "")))
        if db_dir.suffix in (".yaml", ".yml", ".toml"):
            db_dir = db_dir.parent
        return db_dir / ".dex" / "studio.db"
    except Exception:
        return None


def get_studio_db(eng: Any | None = None) -> StudioDb | PgStudioDb | None:
    """Return (or create) the process-level StudioDb / PgStudioDb.

    When ``DATABASE_URL`` is set → returns a ``PgStudioDb`` (multi-pod).
    Otherwise returns a ``StudioDb`` backed by ``studio.db`` on disk (single-pod).

    Accepts an optional engine so callers that already have one don't need to
    import ``_engine``. When ``eng`` is None the function falls back to
    ``get_engine()`` from ``dex_studio._engine``.
    """
    global _GLOBAL_DB, _GLOBAL_DB_PATH
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        if isinstance(_GLOBAL_DB, PgStudioDb):
            return _GLOBAL_DB
        _GLOBAL_DB = PgStudioDb(dsn)
        _GLOBAL_DB_PATH = None
        return _GLOBAL_DB
    if eng is None:
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
        except Exception:
            return None
    if eng is None:
        return None
    db_path = _resolve_sqlite_path(eng)
    if db_path is None:
        return None
    if _GLOBAL_DB is not None and db_path == _GLOBAL_DB_PATH:
        return _GLOBAL_DB
    _GLOBAL_DB = StudioDb(db_path)
    _GLOBAL_DB_PATH = db_path
    return _GLOBAL_DB
