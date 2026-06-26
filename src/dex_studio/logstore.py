"""In-memory ring buffer for application logs — powers the live logs stream."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "LogRecord",
    "LogStore",
    "LogStoreHandler",
    "log_store",
    "structlog_capture_processor",
    "install_stdlib_handler",
]


class LogRecord:
    __slots__ = ("seq", "ts", "level", "logger", "msg")

    def __init__(self, seq: int, ts: str, level: str, logger: str, msg: str) -> None:
        self.seq = seq
        self.ts = ts
        self.level = level
        self.logger = logger
        self.msg = msg


class LogStore:
    """Thread-safe circular buffer for log records."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[LogRecord] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def add(self, level: str, logger: str, msg: str) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._seq += 1
            rec = LogRecord(seq=self._seq, ts=ts, level=level.upper(), logger=logger, msg=msg)
            self._buf.append(rec)

    def since(self, after_seq: int) -> list[LogRecord]:
        """Return all records with seq > after_seq, chronological order."""
        with self._lock:
            return [r for r in self._buf if r.seq > after_seq]

    def recent(self, limit: int = 500) -> list[LogRecord]:
        """Return the most recent `limit` records, newest first."""
        with self._lock:
            items = list(self._buf)
        items.reverse()
        return items[:limit]

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq


log_store = LogStore()


class LogStoreHandler(logging.Handler):
    """stdlib logging handler — mirrors every record into log_store.

    Installed on the root logger (and directly on uvicorn.access which has
    propagate=False) so that uvicorn, FastAPI, and library logs all appear in
    the System / Logs viewer alongside structlog output.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = record.levelname.upper()
            logger_name = record.name
            msg = record.getMessage()
            if record.exc_info:
                import traceback as _tb

                lines = _tb.format_exception(*record.exc_info)
                tail = "".join(lines).strip().replace("\n", " | ")
                msg = f"{msg} | {tail}"
            log_store.add(level, logger_name, msg)
        except Exception:
            pass


def install_stdlib_handler() -> None:
    """Attach LogStoreHandler to root logger + uvicorn.access.

    Call this once during app startup AFTER uvicorn has configured its own
    logging (i.e., inside the FastAPI lifespan startup hook).  At that point
    uvicorn.access already has propagate=False, so we add the handler to it
    directly as well as to root.
    """
    handler = LogStoreHandler()
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    if not any(isinstance(h, LogStoreHandler) for h in root.handlers):
        root.addHandler(handler)
        # Allow DEBUG records from any logger to propagate up to our handler.
        root.setLevel(logging.DEBUG)

    # uvicorn.access sets propagate=False — it won't reach root, so add directly.
    # Do NOT also add to uvicorn / uvicorn.error — they propagate to root already.
    access_lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(h, LogStoreHandler) for h in access_lg.handlers):
        access_lg.addHandler(handler)


def structlog_capture_processor(
    _logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Structlog processor — mirrors every log call into log_store."""
    level = method.upper()
    src = str(event_dict.get("src") or event_dict.get("logger_name") or "app")
    parts = [str(event_dict.get("event", ""))]
    for k, v in event_dict.items():
        if k not in ("event", "timestamp", "level", "_record", "src", "logger_name"):
            parts.append(f"{k}={v}")
    log_store.add(level, src, " ".join(parts))
    return event_dict
