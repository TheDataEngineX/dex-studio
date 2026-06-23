"""DEX Studio-specific SQLite persistence — scheduler state, locks, dead letter.

Separate from dataenginex DexStore so we can add tables without touching
the platform package. Stored at {project_dir}/.dex/studio.db.

Connection strategy: thread-local connections with WAL mode + busy_timeout so
SQLite handles concurrent access natively. Each thread keeps its connection
alive rather than open/close per query.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

__all__ = ["StudioDb", "get_studio_db"]

log = structlog.get_logger().bind(src="studio_db")

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
    status          TEXT NOT NULL DEFAULT 'pending',
    built_at        TEXT,
    updated_at      TEXT NOT NULL
);
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
        status: str = "ok",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        conn = self._conn()
        conn.execute(
            "INSERT INTO embedding_collections"
            " (name, source_table, source_column, model,"
            "  vector_count, status, built_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET"
            "  source_table=excluded.source_table, source_column=excluded.source_column,"
            "  model=excluded.model, vector_count=excluded.vector_count,"
            "  status=excluded.status, built_at=excluded.built_at, updated_at=excluded.updated_at",
            [name, source_table, source_column, model, vector_count, status, now, now],
        )
        conn.commit()

    def get_embedding_collections(self) -> list[dict[str, Any]]:
        rows = (
            self._conn()
            .execute("SELECT * FROM embedding_collections ORDER BY updated_at DESC")
            .fetchall()
        )
        return [dict(r) for r in rows]


# ── Process-level singleton accessor ─────────────────────────────────────────

_GLOBAL_DB: StudioDb | None = None
_GLOBAL_DB_PATH: Path | None = None


def get_studio_db(eng: Any | None = None) -> StudioDb | None:
    """Return (or create) the process-level StudioDb for the active project.

    Accepts an optional engine so callers that already have one don't need to
    import ``_engine``. When ``eng`` is None the function falls back to
    ``get_engine()`` from ``dex_studio._engine``.
    """
    global _GLOBAL_DB, _GLOBAL_DB_PATH
    if eng is None:
        try:
            from dex_studio._engine import get_engine  # lazy — avoid circular at import

            eng = get_engine()
        except Exception:
            return None
    if eng is None:
        return None
    try:
        db_dir = Path(str(getattr(eng, "_dex_dir", None) or getattr(eng, "config_path", "")))
        if db_dir.suffix in (".yaml", ".yml", ".toml"):
            db_dir = db_dir.parent
        db_path = db_dir / ".dex" / "studio.db"
    except Exception:
        return None
    if _GLOBAL_DB is not None and db_path == _GLOBAL_DB_PATH:
        return _GLOBAL_DB
    _GLOBAL_DB = StudioDb(db_path)
    _GLOBAL_DB_PATH = db_path
    return _GLOBAL_DB
