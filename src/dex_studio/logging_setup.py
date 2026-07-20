"""Central logging configuration for dex-studio.

One place wires three concerns that were previously spread across app.py and
logstore.py:

* **structlog pipeline** (application code): JSON when stdout is piped
  (containers), pretty console on a TTY (development). Level comes from
  ``DEX_STUDIO_LOG_LEVEL`` (default ``INFO``); format can be forced with
  ``DEX_STUDIO_LOG_FORMAT=json|console``.
* **stdlib bridge** (uvicorn, FastAPI, third-party libraries): their records
  are rendered through the *same* structlog renderer, so every stdout line —
  app or library — has one consistent shape.
* **LogStore capture** (System / Logs viewer in the UI): stdlib records are
  mirrored at DEBUG regardless of the stdout level; structlog events are
  mirrored via :func:`~dex_studio.logstore.structlog_capture_processor` and
  follow the configured level.

Call :func:`setup_logging` once, before the app object is created. Calling it
again is a no-op (idempotent), so tests and reloads are safe.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

from dex_studio.logstore import LogStoreHandler, structlog_capture_processor

_CONFIGURED = False

# Processors shared by app events and foreign (stdlib) records so both render
# with the same fields. add_logger_name is stdlib-only (needs logger.name) and
# lives in the foreign chain; app events carry src= from get_logger() instead.
_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=False),
    structlog.processors.StackInfoRenderer(),
]

_APP_PROCESSORS: list[structlog.typing.Processor] = [
    *_SHARED_PROCESSORS,
    structlog_capture_processor,
]
_FOREIGN_PRE_CHAIN: list[structlog.typing.Processor] = [
    structlog.stdlib.add_logger_name,
    *_SHARED_PROCESSORS,
]


def _stdout_level() -> int:
    name = os.environ.get("DEX_STUDIO_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _use_json() -> bool:
    forced = os.environ.get("DEX_STUDIO_LOG_FORMAT", "").lower()
    if forced == "json":
        return True
    if forced == "console":
        return False
    return hasattr(sys.stdout, "isatty") and not sys.stdout.isatty()


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level = _stdout_level()
    if _use_json():
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
        tail = [structlog.processors.format_exc_info, renderer]
    else:
        # ConsoleRenderer formats exc_info itself — no format_exc_info needed
        renderer = structlog.dev.ConsoleRenderer()
        tail = [renderer]

    # ── Application events (structlog) ───────────────────────────────────────
    structlog.configure(
        processors=[*_APP_PROCESSORS, *tail],  # type: ignore[list-item]
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # ── Foreign records (uvicorn, FastAPI, libraries) ─────────────────────────
    # Rendered with the same renderer via ProcessorFormatter; captured to the
    # UI LogStore at DEBUG independently of the stdout level.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *tail],  # type: ignore[list-item]
        foreign_pre_chain=_FOREIGN_PRE_CHAIN,
    )
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)

    store_handler = LogStoreHandler()
    store_handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stdout_handler)
    root.addHandler(store_handler)
    root.setLevel(logging.DEBUG)  # sinks filter; root stays open for capture

    bridge_uvicorn()

    # Noisy-by-default libraries stay at INFO even when the app runs DEBUG.
    for name in ("watchfiles", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(max(level, logging.INFO))


def bridge_uvicorn() -> None:
    """Route uvicorn's loggers through the root handlers.

    uvicorn attaches its own handlers when the server starts (uvicorn.access
    even sets propagate=False), which happens *after* module import — so call
    this again from app lifespan startup to strip them once they exist.
    Idempotent.
    """
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def get_logger(src: str) -> structlog.typing.FilteringBoundLogger:
    """Project convention: ``logger = get_logger("app")``."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger()
    return logger.bind(src=src)


def log_format() -> str:
    """Resolved output format ("json" or "console") — for startup banners."""
    return "json" if _use_json() else "console"
