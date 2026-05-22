"""In-memory ring buffer for application logs — powers the live logs stream."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from typing import Any

__all__ = ["LogRecord", "LogStore", "log_store", "structlog_capture_processor"]

_LEVEL_ORDER: dict[str, int] = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 3}


class LogRecord:
    __slots__ = ("ts", "level", "msg")

    def __init__(self, ts: str, level: str, msg: str) -> None:
        self.ts = ts
        self.level = level
        self.msg = msg


class LogStore:
    """Thread-safe circular buffer for log records."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[LogRecord] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def add(self, level: str, msg: str) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._buf.append(LogRecord(ts=ts, level=level.upper(), msg=msg))
            self._seq += 1

    def recent(self, limit: int = 200, min_level: str = "DEBUG") -> list[LogRecord]:
        min_n = _LEVEL_ORDER.get(min_level.upper(), 0)
        with self._lock:
            items = list(self._buf)
        items.reverse()
        return [r for r in items if _LEVEL_ORDER.get(r.level, 0) >= min_n][:limit]

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq


log_store = LogStore()


def structlog_capture_processor(
    _logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Structlog processor that mirrors every log call into log_store."""
    level = method.upper()
    parts = [str(event_dict.get("event", ""))]
    for k, v in event_dict.items():
        if k not in ("event", "timestamp", "level", "_record"):
            parts.append(f"{k}={v}")
    log_store.add(level, " ".join(parts))
    return event_dict
