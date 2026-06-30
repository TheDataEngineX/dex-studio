"""Shared persistent store backed by DATABASE_URL (Postgres required).

This module provides the key/value settings store and project registry
used by auth.py and config.py.  All I/O is synchronous — FastAPI runs
sync handler functions in a threadpool, so no async plumbing is needed.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy import Connection, Engine

__all__ = [
    "init_db",
    "get_setting",
    "set_setting",
    "delete_setting",
    "get_projects",
    "set_project",
    "delete_project",
]

_log = structlog.getLogger().bind(src="db_store")

_engine: Engine | None = None

# ---------------------------------------------------------------------------
# DDL — two simple tables, no ORM models needed
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create tables and initialise the module-level engine.

    Raises RuntimeError if DATABASE_URL is not set.
    Must be called once at app startup before any other function.
    """
    from sqlalchemy import create_engine, text

    global _engine  # noqa: PLW0603

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Set it to a Postgres connection string, e.g. "
            "postgresql+psycopg://user:pass@host:5432/dbname"
        )

    _engine = create_engine(url, pool_pre_ping=True)
    with _engine.begin() as conn:
        for statement in _DDL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    _log.info("db initialised", url=_redact(url))


def _redact(url: str) -> str:
    """Return the URL with the password replaced by ***."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(parsed.password, "***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:  # noqa: BLE001
        pass
    return url


@contextlib.contextmanager
def _get_conn() -> Generator[Connection, None, None]:
    """Yield a connection from the engine, raising if init_db() was not called."""
    if _engine is None:
        raise RuntimeError("db_store.init_db() has not been called")
    with _engine.begin() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Settings (key/value)
# ---------------------------------------------------------------------------


def get_setting(key: str) -> str | None:
    """Return the stored value for *key*, or None if not found."""
    from sqlalchemy import text

    with _get_conn() as conn:
        row = conn.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key}).fetchone()
        return str(row[0]) if row else None


def set_setting(key: str, value: str) -> None:
    """Upsert *key* = *value* in the settings table."""
    from sqlalchemy import text

    # Portable upsert — works on both Postgres and SQLite
    with _get_conn() as conn:
        conn.execute(
            text(
                "INSERT INTO settings (key, value, updated_at) VALUES (:k, :v, CURRENT_TIMESTAMP) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                "updated_at = CURRENT_TIMESTAMP"
            ),
            {"k": key, "v": value},
        )


def delete_setting(key: str) -> None:
    """Remove *key* from the settings table (no-op if absent)."""
    from sqlalchemy import text

    with _get_conn() as conn:
        conn.execute(text("DELETE FROM settings WHERE key = :k"), {"k": key})


# ---------------------------------------------------------------------------
# Projects registry
# ---------------------------------------------------------------------------


def get_projects() -> list[tuple[str, str]]:
    """Return all projects as a list of (name, config_path) tuples."""
    from sqlalchemy import text

    with _get_conn() as conn:
        rows = conn.execute(
            text("SELECT name, config_path FROM projects ORDER BY created_at")
        ).fetchall()
        return [(str(r[0]), str(r[1])) for r in rows]


def set_project(name: str, config_path: str) -> None:
    """Upsert a project record."""
    from sqlalchemy import text

    with _get_conn() as conn:
        conn.execute(
            text(
                "INSERT INTO projects (name, config_path) VALUES (:n, :p) "
                "ON CONFLICT (name) DO UPDATE SET config_path = EXCLUDED.config_path"
            ),
            {"n": name, "p": config_path},
        )


def delete_project(name: str) -> None:
    """Remove a project by name (no-op if absent)."""
    from sqlalchemy import text

    with _get_conn() as conn:
        conn.execute(text("DELETE FROM projects WHERE name = :n"), {"n": name})
