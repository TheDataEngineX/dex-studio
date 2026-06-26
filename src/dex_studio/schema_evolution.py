"""Schema drift detection and contract management for DEX Studio.

Compares the current schema of a lakehouse parquet against the stored
contract in StudioDb. Records drift events when columns are added,
removed, or change type. Contracts can be accepted (promoting the new
schema) or left open for review.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import structlog

from dex_studio.studio_db import StudioDb

__all__ = ["SchemaEvolutionManager", "DriftEvent"]

log = structlog.get_logger().bind(src="schema_evolution")


class DriftEvent:
    """Describes one column-level change between contract and observed schema."""

    __slots__ = ("kind", "column", "old_type", "new_type")

    def __init__(
        self,
        kind: str,
        column: str,
        old_type: str = "",
        new_type: str = "",
    ) -> None:
        # kind: "added" | "removed" | "type_changed"
        self.kind = kind
        self.column = column
        self.old_type = old_type
        self.new_type = new_type

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "column": self.column,
            "old_type": self.old_type,
            "new_type": self.new_type,
        }


class SchemaEvolutionManager:
    """Detects schema drift and stores contracts for lakehouse pipelines."""

    def __init__(self, project_dir: Path, db: StudioDb) -> None:
        self._root = project_dir / ".dex" / "lakehouse"
        self._db = db

    def _parquet_path(self, pipeline: str) -> Path | None:
        for layer in ("bronze", "silver", "gold"):
            p = self._root / layer / f"{pipeline}.parquet"
            if p.exists():
                return p
        return None

    def _read_schema(self, path: Path) -> dict[str, str]:
        """Return {column: type} from the parquet file's schema."""
        import duckdb

        schema: dict[str, str] = {}
        with contextlib.suppress(Exception), duckdb.connect() as conn:
            rows = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
            for row in rows:
                schema[row[0]] = str(row[1])
        return schema

    def _diff(self, contract: dict[str, str], observed: dict[str, str]) -> list[DriftEvent]:
        events: list[DriftEvent] = []
        for col, typ in observed.items():
            if col not in contract:
                events.append(DriftEvent("added", col, new_type=typ))
            elif contract[col] != typ:
                events.append(DriftEvent("type_changed", col, old_type=contract[col], new_type=typ))
        for col in contract:
            if col not in observed:
                events.append(DriftEvent("removed", col, old_type=contract[col]))
        return events

    def snapshot_contract(self, pipeline: str) -> dict[str, str] | None:
        """Read current schema and store as the active contract. Returns schema or None."""
        path = self._parquet_path(pipeline)
        if path is None:
            return None
        schema = self._read_schema(path)
        if not schema:
            return None
        self._db.set_schema_contract(pipeline, schema)
        log.info("schema contract recorded", pipeline=pipeline, columns=len(schema))
        return schema

    def check_drift(self, pipeline: str) -> list[DriftEvent]:
        """Compare current schema against stored contract. Records drift if found."""
        contract_record = self._db.get_schema_contract(pipeline)
        if contract_record is None:
            return []
        contract = contract_record["columns"]
        path = self._parquet_path(pipeline)
        if path is None:
            return []
        observed = self._read_schema(path)
        if not observed:
            return []
        events = self._diff(contract, observed)
        if events:
            self._db.record_drift(pipeline, [e.to_dict() for e in events])
            log.warning(
                "schema drift detected",
                pipeline=pipeline,
                changes=len(events),
            )
        return events

    def accept_drift(self, event_id: int, pipeline: str) -> None:
        """Accept a drift event: promote observed schema to new contract."""
        self._db.accept_drift(event_id)
        self.snapshot_contract(pipeline)
        log.info("drift accepted, contract updated", pipeline=pipeline, event_id=event_id)

    def drift_summary(self) -> list[dict[str, Any]]:
        """Return all drift events (with accepted status) for the UI."""
        return self._db.get_drift_events()

    def check_all(self, pipelines: dict[str, Any]) -> dict[str, list[DriftEvent]]:
        """Run drift check for every pipeline that has a contract."""
        results: dict[str, list[DriftEvent]] = {}
        for name in pipelines:
            try:
                results[name] = self.check_drift(name)
            except Exception as exc:
                log.warning("drift check error", pipeline=name, error=str(exc))
        return results
