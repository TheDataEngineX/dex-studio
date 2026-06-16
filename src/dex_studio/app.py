"""DEX Studio — FastAPI application factory."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from dex_studio.logstore import structlog_capture_processor
from dex_studio.utils import fmt_bytes, fmt_cron, fmt_ts, status_color

structlog.configure(
    processors=[
        structlog_capture_processor,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.getLogger()


class _SelectiveGZip:
    """GZip compression for normal responses, bypassed for SSE/streaming
    endpoints — gzip buffers streamed chunks and would break Server-Sent Events.
    """

    def __init__(self, app: ASGIApp, minimum_size: int = 1024) -> None:
        self._app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path.endswith("/stream"):
            await self._app(scope, receive, send)
        else:
            await self._gzip(scope, receive, send)


_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def _session_secret() -> str:
    """Return or generate a persistent session signing secret."""
    key_file = Path.home() / ".dex-studio" / "session.key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key


def make_templates() -> Jinja2Templates:
    """Create the Jinja2 environment with custom filters."""
    t = Jinja2Templates(directory=str(TEMPLATES_DIR))
    t.env.filters["fmt_ts"] = fmt_ts
    t.env.filters["fmt_cron"] = fmt_cron
    t.env.filters["fmt_bytes"] = fmt_bytes
    t.env.filters["status_color"] = status_color
    t.env.globals["enumerate"] = enumerate
    t.env.globals["zip"] = zip
    return t


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    import contextlib

    from dex_studio._engine import get_engine
    from dex_studio.scheduler import start_scheduler, stop_scheduler

    # Pre-warm: open SQLite WAL + run CREATE TABLE IF NOT EXISTS before the
    # first HTTP request. Suppressed so a missing/unconfigured project never
    # blocks startup.
    with contextlib.suppress(Exception):
        get_engine()

    start_scheduler(_app)
    try:
        yield
    finally:
        await stop_scheduler(_app)
        with contextlib.suppress(Exception):
            from dex_studio.jobs import _EXECUTOR

            _EXECUTOR.shutdown(wait=False)
        with contextlib.suppress(Exception):
            from dex_studio._engine import _ENGINE

            if _ENGINE is not None:
                _ENGINE.close()


def create_app() -> FastAPI:
    """FastAPI application factory — called by uvicorn --factory."""
    from fastapi import Request
    from fastapi.responses import RedirectResponse

    from dex_studio.auth import RequiresEngine, RequiresLogin
    from dex_studio.routers import ai, data, ml, root, secops, system

    app = FastAPI(
        title="DEX Studio",
        description="DataEngineX control plane",
        version="0.3.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    @app.exception_handler(RequiresLogin)
    async def _handle_requires_login(request: Request, exc: RequiresLogin) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=303)

    @app.exception_handler(RequiresEngine)
    async def _handle_requires_engine(request: Request, exc: RequiresEngine) -> RedirectResponse:
        return RedirectResponse(url="/onboarding", status_code=303)

    # ── Session middleware ────────────────────────────────────────────────────
    secret = os.environ.get("DEX_STUDIO_SESSION_SECRET") or _session_secret()
    https_only = os.environ.get("DEX_HTTPS", "").lower() in ("1", "true", "yes")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="dex_session",
        https_only=https_only,
    )

    # ── Compression (bandwidth) + request timing (latency observability) ──────
    app.add_middleware(_SelectiveGZip, minimum_size=1024)

    @app.middleware("http")
    async def _security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                # Alpine.js v3 requires unsafe-eval (uses new Function() for expressions)
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            ),
        )
        return response

    @app.middleware("http")
    async def _timing(request: Any, call_next: Any) -> Any:
        import time as _time

        start = _time.perf_counter()
        response = await call_next(request)
        dur_ms = (_time.perf_counter() - start) * 1000
        response.headers["Server-Timing"] = f"app;dur={dur_ms:.1f}"
        if dur_ms > 1000:
            logger.warning(
                "slow request", path=request.url.path, method=request.method, ms=round(dur_ms)
            )
        return response

    # ── Static files ─────────────────────────────────────────────────────────
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ── Templates (shared singleton) ─────────────────────────────────────────
    templates = make_templates()
    app.state.templates = templates  # type: ignore[attr-defined]

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(root.router)
    app.include_router(data.router, prefix="/data")
    app.include_router(ml.router, prefix="/ml")
    app.include_router(ai.router, prefix="/ai")
    app.include_router(secops.router, prefix="/secops")
    app.include_router(system.router, prefix="/system")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "favicon.svg"), media_type="image/svg+xml")

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        from dex_studio._engine import get_engine as _ge

        eng = _ge()
        status = eng.health() if eng else {"status": "no engine"}
        return {"status": status.get("status", "unknown")}

    logger.info("DEX Studio started", port=7860)
    return app


# ── Template helpers used across routers ────────────────────────────────────


def get_templates(app: Any) -> Jinja2Templates:
    return app.state.templates  # type: ignore[no-any-return]
