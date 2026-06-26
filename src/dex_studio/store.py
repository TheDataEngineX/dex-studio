"""StudioStore — lightweight reactive pub/sub store for cross-page state.

Pages publish events; other pages subscribe and update without full reload.

Usage::

    # Publisher (e.g., after running a pipeline):
    store = get_store()
    store.emit("pipeline_run", {"name": "ingest", "status": "success"})

    # Subscriber (e.g., system status page):
    # No public subscribe API — use emit() and listen via middleware
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = ["StudioStore", "get_store"]

_log = logging.getLogger(__name__)

# Singleton store instance
_store: StudioStore | None = None


@dataclass
class _Notification:
    """A cross-page notification bubble."""

    message: str
    type: str = "info"  # info | success | warning | error
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    read: bool = False
    route: str = ""  # optional deep-link


class StudioStore:
    """Singleton reactive store for DEX Studio.

    - ``pipeline_runs``: tracks live run state by pipeline name
    - ``notifications``: FIFO notification queue (capped at 100)
    - Event bus: arbitrary ``emit``/``on`` pub/sub
    """

    def __init__(self) -> None:
        self.pipeline_runs: dict[str, str] = {}  # name → status
        self.notifications: deque[_Notification] = deque(maxlen=100)
        self._listeners: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Pipeline run state
    # ------------------------------------------------------------------

    def set_pipeline_status(self, name: str, status: str) -> None:
        """Update pipeline run status and emit a ``pipeline_run`` event."""
        self.pipeline_runs[name] = status
        self.emit("pipeline_run", {"name": name, "status": status})
        if status in ("success", "failure"):
            self.notify(
                f"Pipeline '{name}' {status}",
                type="positive" if status == "success" else "negative",
                route="/data/pipelines",
            )

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def notify(self, message: str, *, type: str = "info", route: str = "") -> None:
        """Push a notification into the queue and emit ``notification`` event."""
        n = _Notification(message=message, type=type, route=route)
        self.notifications.appendleft(n)
        self.emit("notification", {"message": message, "type": type, "route": route})

    def emit(self, event: str, payload: Any = None) -> None:
        """Publish an event to all subscribers."""
        for handler in list(self._listeners.get(event, [])):
            try:
                handler(payload)
            except Exception:
                _log.exception("StudioStore handler error for event=%s", event)


def get_store() -> StudioStore:
    """Return the singleton StudioStore, creating it on first call."""
    global _store
    if _store is None:
        _store = StudioStore()
    return _store
