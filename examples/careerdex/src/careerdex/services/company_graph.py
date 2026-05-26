"""CompanyGraph service — DuckDB-backed graph for tracking company connections."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import structlog

from careerdex.services.graph import CompanyNode, ConnectionEdge, ConnectionType

logger = structlog.get_logger()

__all__ = ["CompanyGraph"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "company_graph.duckdb"

_CREATE_TABLE_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    id                      VARCHAR PRIMARY KEY,
    name                    VARCHAR NOT NULL,
    url                     VARCHAR DEFAULT '',
    industry                VARCHAR DEFAULT '',
    size                    VARCHAR DEFAULT '',
    logo_url                VARCHAR DEFAULT '',
    metadata_json           VARCHAR DEFAULT '{}'
);
"""

_CREATE_TABLE_CONNECTIONS = """
CREATE TABLE IF NOT EXISTS connections (
    id                      VARCHAR PRIMARY KEY,
    source_company_id        VARCHAR NOT NULL,
    target_company_id        VARCHAR NOT NULL,
    connection_type         VARCHAR NOT NULL,
    strength                DOUBLE DEFAULT 1.0,
    notes                   VARCHAR DEFAULT '',
    created_at              TIMESTAMP NOT NULL,
    FOREIGN KEY (source_company_id) REFERENCES companies(id),
    FOREIGN KEY (target_company_id) REFERENCES companies(id)
);
"""


class CompanyGraph:
    """DuckDB-backed company graph store.

    Usage::

        graph = CompanyGraph()
        company = CompanyNode(name="Acme", url="https://acme.com", industry="Tech")
        graph.add_company(company)
        comp = graph.get_company(company.id)
        graph.add_connection(company.id, other_id, "competitors", 0.8)
        connections = graph.get_connections(company.id)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_CREATE_TABLE_COMPANIES)
        self._conn.execute(_CREATE_TABLE_CONNECTIONS)
        logger.info("company_graph_ready", db=str(self._db_path))

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()

    # -- CRUD -------------------------------------------------------------

    def add_company(self, company: CompanyNode) -> CompanyNode:
        """Insert a company node."""
        self._conn.execute(
            """
            INSERT INTO companies (id, name, url, industry, size, logo_url, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                url = excluded.url,
                industry = excluded.industry,
                size = excluded.size,
                logo_url = excluded.logo_url,
                metadata_json = excluded.metadata_json
            """,
            [
                company.id,
                company.name,
                company.url,
                company.industry,
                company.size,
                company.logo_url,
                json.dumps(company.metadata),
            ],
        )
        logger.info("company_added", id=company.id, name=company.name)
        return company

    def get_company(self, company_id: str) -> CompanyNode | None:
        """Fetch a company node by ID."""
        result = self._conn.execute("SELECT * FROM companies WHERE id = ?", [company_id]).fetchone()
        if result is None:
            return None
        return self._row_to_company(result)

    def update_company(self, company: CompanyNode) -> CompanyNode:
        """Update an existing company node."""
        self.add_company(company)
        return company

    def add_connection(
        self,
        source_company_id: str,
        target_company_id: str,
        connection_type: str | ConnectionType = ConnectionType.COMPETITORS,
        strength: float = 1.0,
        notes: str = "",
    ) -> ConnectionEdge:
        """Add a connection between two companies."""
        conn_type = (
            ConnectionType(connection_type) if isinstance(connection_type, str) else connection_type
        )
        edge = ConnectionEdge(
            source_company_id=source_company_id,
            target_company_id=target_company_id,
            connection_type=conn_type,
            strength=strength,
            notes=notes,
        )
        self._conn.execute(
            """
            INSERT INTO connections (
                id, source_company_id, target_company_id,
                connection_type, strength, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                source_company_id = excluded.source_company_id,
                target_company_id = excluded.target_company_id,
                connection_type = excluded.connection_type,
                strength = excluded.strength,
                notes = excluded.notes,
                created_at = excluded.created_at
            """,
            [
                edge.id,
                edge.source_company_id,
                edge.target_company_id,
                edge.connection_type.value,
                edge.strength,
                edge.notes,
                edge.created_at.isoformat(),
            ],
        )
        logger.info(
            "connection_added",
            id=edge.id,
            source=source_company_id,
            target=target_company_id,
            type=conn_type.value,
        )
        return edge

    def get_connections(self, company_id: str) -> list[ConnectionEdge]:
        """Get all connections for a company (both as source and target)."""
        rows = self._conn.execute(
            """
            SELECT * FROM connections
            WHERE source_company_id = ? OR target_company_id = ?
            ORDER BY created_at DESC
            """,
            [company_id, company_id],
        ).fetchall()
        return [self._row_to_connection(row) for row in rows]

    # -- private ----------------------------------------------------------

    def _row_to_company(self, row: tuple[object, ...]) -> CompanyNode:
        """Convert a DuckDB row to a CompanyNode."""
        (
            id_,
            name,
            url,
            industry,
            size,
            logo_url,
            metadata_json,
        ) = row
        return CompanyNode(
            id=str(id_),
            name=str(name),
            url=str(url or ""),
            industry=str(industry or ""),
            size=str(size or ""),
            logo_url=str(logo_url or ""),
            metadata=json.loads(str(metadata_json or "{}")),
        )

    def _row_to_connection(self, row: tuple[object, ...]) -> ConnectionEdge:
        """Convert a DuckDB row to a ConnectionEdge."""
        (
            id_,
            source_company_id,
            target_company_id,
            connection_type,
            strength,
            notes,
            created_at,
        ) = row
        return ConnectionEdge(
            id=str(id_),
            source_company_id=str(source_company_id),
            target_company_id=str(target_company_id),
            connection_type=ConnectionType(str(connection_type)),
            strength=float(str(strength)) if strength is not None else 1.0,
            notes=str(notes or ""),
            created_at=_ensure_tz(created_at),
        )


def _ensure_tz(value: object) -> datetime:
    """Ensure a value is a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
