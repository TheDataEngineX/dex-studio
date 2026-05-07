"""Audit logging — track all user actions and system events."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.getLogger()

__all__ = ["AuditLogger", "AuditEvent"]


@dataclass
class AuditEvent:
    """A single audit event."""

    event_id: str = field(default_factory=lambda: datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S%f"))
    timestamp: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    actor: str = "system"
    action: str = ""
    resource: str = ""
    resource_type: str = ""
    status: str = "success"
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Persistent audit log backed by JSON file."""

    def __init__(self, persist_path: str | Path) -> None:
        self._persist_path = Path(persist_path)
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()
        if self._persist_path.exists():
            self._load()

    def log(
        self,
        action: str,
        resource: str = "",
        resource_type: str = "",
        actor: str = "user",
        status: str = "success",
        details: dict[str, Any] | None = None,
        ip_address: str = "",
    ) -> AuditEvent:
        """Log an audit event."""
        event = AuditEvent(
            action=action,
            resource=resource,
            resource_type=resource_type,
            actor=actor,
            status=status,
            details=details or {},
            ip_address=ip_address,
        )
        with self._lock:
            self._events.append(event)
            self._save()
        return event

    def get_events(
        self,
        action: str | None = None,
        resource: str | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit events with filters."""
        results = list(reversed(self._events))
        if action:
            results = [e for e in results if action.lower() in e.action.lower()]
        if resource:
            results = [e for e in results if resource.lower() in e.resource.lower()]
        if actor:
            results = [e for e in results if actor.lower() in e.actor.lower()]
        return results[:limit]

    @property
    def all_events(self) -> list[AuditEvent]:
        """All events, newest first."""
        return list(reversed(self._events))

    def _save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps([e.to_dict() for e in self._events], indent=2, default=str)
        )

    def _load(self) -> None:
        try:
            raw = json.loads(self._persist_path.read_text())
            for item in raw:
                self._events.append(AuditEvent(**item))
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("audit log corrupted, starting fresh", error=str(exc))
            self._events = []
