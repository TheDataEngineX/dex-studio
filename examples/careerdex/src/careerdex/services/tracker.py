"""Application tracker — DuckDB-backed CRUD for job applications.

Stores all application data in a local DuckDB database at
``~/.dex-studio/careerdex/applications.duckdb``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import structlog

from careerdex.models.application import (
    ApplicationEntry,
    ApplicationEvent,
    ApplicationNote,
    ApplicationStatus,
)

logger = structlog.get_logger()

__all__ = ["ApplicationTracker"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "applications.duckdb"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id              VARCHAR PRIMARY KEY,
    company         VARCHAR NOT NULL,
    position        VARCHAR NOT NULL,
    url             VARCHAR DEFAULT '',
    location        VARCHAR DEFAULT '',
    salary_min      DOUBLE,
    salary_max      DOUBLE,
    salary_currency VARCHAR DEFAULT 'USD',
    status          VARCHAR NOT NULL DEFAULT 'saved',
    source          VARCHAR DEFAULT '',
    contact_name    VARCHAR DEFAULT '',
    contact_email   VARCHAR DEFAULT '',
    notes_json      VARCHAR DEFAULT '[]',
    events_json     VARCHAR DEFAULT '[]',
    tags_json       VARCHAR DEFAULT '[]',
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    applied_at      TIMESTAMP,
    next_follow_up  TIMESTAMP
);
"""


class ApplicationTracker:
    """DuckDB-backed application tracker.

    Usage::

        tracker = ApplicationTracker()
        tracker.add(ApplicationEntry(company="Acme", position="SWE"))
        apps = tracker.list_all()
        tracker.update_status(app_id, ApplicationStatus.APPLIED)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_CREATE_TABLE)
        logger.info("tracker_ready", db=str(self._db_path))

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()

    # -- CRUD -------------------------------------------------------------

    def add(self, entry: ApplicationEntry) -> ApplicationEntry:
        """Insert a new application."""
        self._conn.execute(
            """
            INSERT INTO applications (
                id, company, position, url, location,
                salary_min, salary_max, salary_currency,
                status, source, contact_name, contact_email,
                notes_json, events_json, tags_json,
                created_at, updated_at, applied_at, next_follow_up
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entry.id,
                entry.company,
                entry.position,
                entry.url,
                entry.location,
                entry.salary_min,
                entry.salary_max,
                entry.salary_currency,
                entry.status.value,
                entry.source,
                entry.contact_name,
                entry.contact_email,
                json.dumps([n.model_dump(mode="json") for n in entry.notes]),
                json.dumps([e.model_dump(mode="json") for e in entry.events]),
                json.dumps(entry.tags),
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
                entry.applied_at.isoformat() if entry.applied_at else None,
                entry.next_follow_up.isoformat() if entry.next_follow_up else None,
            ],
        )
        logger.info("application_added", id=entry.id, company=entry.company)
        return entry

    def get(self, app_id: str) -> ApplicationEntry | None:
        """Fetch a single application by ID."""
        result = self._conn.execute("SELECT * FROM applications WHERE id = ?", [app_id]).fetchone()
        if result is None:
            return None
        return self._row_to_entry(result)

    def list_all(
        self,
        status: ApplicationStatus | None = None,
        search: str = "",
    ) -> list[ApplicationEntry]:
        """List applications, optionally filtered by status or search term."""
        query = "SELECT * FROM applications"
        params: list[object] = []
        conditions: list[str] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if search:
            conditions.append("(LOWER(company) LIKE ? OR LOWER(position) LIKE ?)")
            term = f"%{search.lower()}%"
            params.extend([term, term])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def update(self, entry: ApplicationEntry) -> None:
        """Update an existing application (full replace)."""
        entry.updated_at = datetime.now(UTC)
        self._conn.execute(
            """
            UPDATE applications SET
                company = ?, position = ?, url = ?, location = ?,
                salary_min = ?, salary_max = ?, salary_currency = ?,
                status = ?, source = ?, contact_name = ?, contact_email = ?,
                notes_json = ?, events_json = ?, tags_json = ?,
                updated_at = ?, applied_at = ?, next_follow_up = ?
            WHERE id = ?
            """,
            [
                entry.company,
                entry.position,
                entry.url,
                entry.location,
                entry.salary_min,
                entry.salary_max,
                entry.salary_currency,
                entry.status.value,
                entry.source,
                entry.contact_name,
                entry.contact_email,
                json.dumps([n.model_dump(mode="json") for n in entry.notes]),
                json.dumps([e.model_dump(mode="json") for e in entry.events]),
                json.dumps(entry.tags),
                entry.updated_at.isoformat(),
                entry.applied_at.isoformat() if entry.applied_at else None,
                entry.next_follow_up.isoformat() if entry.next_follow_up else None,
                entry.id,
            ],
        )

    def delete(self, app_id: str) -> bool:
        """Delete an application by ID. Returns True if it existed."""
        existing = self.get(app_id)
        if existing is None:
            return False
        self._conn.execute("DELETE FROM applications WHERE id = ?", [app_id])
        logger.info("application_deleted", id=app_id)
        return True

    def update_status(
        self,
        app_id: str,
        new_status: ApplicationStatus,
        reason: str = "",
    ) -> ApplicationEntry:
        """Transition an application to a new status."""
        entry = self.get(app_id)
        if entry is None:
            raise KeyError(app_id)
        entry.transition(new_status, reason=reason)
        self.update(entry)
        logger.info(
            "status_changed",
            id=app_id,
            from_status=entry.events[-1].from_status,
            to_status=new_status.value,
        )
        return entry

    def add_note(self, app_id: str, text: str) -> ApplicationEntry | None:
        """Add a note to an application."""
        entry = self.get(app_id)
        if entry is None:
            return None
        entry.notes.append(ApplicationNote(text=text))
        self.update(entry)
        return entry

    # -- stats ------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Return counts by status."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM applications GROUP BY status"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def total(self) -> int:
        """Total number of tracked applications."""
        result = self._conn.execute("SELECT COUNT(*) FROM applications").fetchone()
        return result[0] if result else 0

    # -- private ----------------------------------------------------------

    def _row_to_entry(self, row: tuple[object, ...]) -> ApplicationEntry:
        """Convert a DuckDB row to an ApplicationEntry."""
        # Column order matches _CREATE_TABLE
        (
            id_,
            company,
            position,
            url,
            location,
            salary_min,
            salary_max,
            salary_currency,
            status,
            source,
            contact_name,
            contact_email,
            notes_json,
            events_json,
            tags_json,
            created_at,
            updated_at,
            applied_at,
            next_follow_up,
        ) = row

        return ApplicationEntry(
            id=str(id_),
            company=str(company),
            position=str(position),
            url=str(url or ""),
            location=str(location or ""),
            salary_min=float(str(salary_min)) if salary_min is not None else None,
            salary_max=float(str(salary_max)) if salary_max is not None else None,
            salary_currency=str(salary_currency or "USD"),
            status=ApplicationStatus(str(status)),
            source=str(source or ""),
            contact_name=str(contact_name or ""),
            contact_email=str(contact_email or ""),
            notes=_parse_notes(str(notes_json or "[]")),
            events=_parse_events(str(events_json or "[]")),
            tags=json.loads(str(tags_json or "[]")),
            created_at=_ensure_tz(created_at),
            updated_at=_ensure_tz(updated_at),
            applied_at=_ensure_tz(applied_at) if applied_at else None,
            next_follow_up=_ensure_tz(next_follow_up) if next_follow_up else None,
        )


def _ensure_tz(value: object) -> datetime:
    """Ensure a value is a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)


def _parse_notes(raw: str) -> list[ApplicationNote]:
    """Parse notes JSON back to model list."""
    try:
        items = json.loads(raw)
        return [ApplicationNote(**n) for n in items]
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_events(raw: str) -> list[ApplicationEvent]:
    """Parse events JSON back to model list."""
    try:
        items = json.loads(raw)
        return [ApplicationEvent(**e) for e in items]
    except (json.JSONDecodeError, TypeError):
        return []
