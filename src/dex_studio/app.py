"""DEX Studio — FastAPI application factory."""

from __future__ import annotations

import os
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

from dex_studio import __version__
from dex_studio.logstore import install_stdlib_handler, structlog_capture_processor
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

logger = structlog.getLogger().bind(src="app")


class _SelectiveGZip:
    """GZip compression for normal responses, bypassed for SSE/streaming
    endpoints — gzip buffers streamed chunks and would break Server-Sent Events.
    """

    def __init__(self, app: ASGIApp, minimum_size: int = 1024) -> None:
        self._app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path.endswith("/stream") or "/stream" in path:
            await self._app(scope, receive, send)
        else:
            await self._gzip(scope, receive, send)


_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"



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
    from dex_studio.auth import setup_password
    from dex_studio.db_store import init_db
    from dex_studio.scheduler import start_scheduler, stop_scheduler

    init_db()
    setup_password()
    logger.info("DEX Studio starting up", version=__version__, port=7860)

    # Mirror all stdlib logging (uvicorn, fastapi, libraries) into the log viewer.
    # Must run here — AFTER uvicorn has configured its own logging handlers so we
    # can also attach directly to uvicorn.access (which has propagate=False).
    install_stdlib_handler()

    # Pre-warm: open SQLite WAL + run CREATE TABLE IF NOT EXISTS before the
    # first HTTP request. Suppressed so a missing/unconfigured project never
    # blocks startup.
    eng = None
    with contextlib.suppress(Exception):
        eng = get_engine()
    if eng is not None:
        project_name = ""
        with contextlib.suppress(Exception):
            project_name = str(eng.config.project.name)
        logger.info("engine connected", project=project_name or "unknown")
    else:
        logger.warning("no engine at startup — waiting for project selection via onboarding")

    start_scheduler(_app)
    logger.info("scheduler started")
    try:
        yield
    finally:
        logger.info("DEX Studio shutting down")
        await stop_scheduler(_app)
        logger.info("scheduler stopped")
        with contextlib.suppress(Exception):
            from dex_studio.jobs import _EXECUTOR

            _EXECUTOR.shutdown(wait=False)
        with contextlib.suppress(Exception):
            from dex_studio._engine import _ENGINE

            if _ENGINE is not None:
                _ENGINE.close()
                logger.info("engine closed")


def _register_exception_handlers(app: FastAPI) -> None:
    from fastapi import Request
    from fastapi.responses import RedirectResponse

    from dex_studio.auth import RequiresEngine, RequiresLogin, has_password

    @app.exception_handler(RequiresLogin)
    async def _handle_requires_login(request: Request, exc: RequiresLogin) -> RedirectResponse:
        if not has_password():
            return RedirectResponse(url="/setup", status_code=303)
        return RedirectResponse(url="/login", status_code=303)

    @app.exception_handler(RequiresEngine)
    async def _handle_requires_engine(request: Request, exc: RequiresEngine) -> Any:
        from dex_studio.routers._deps import _has_project_config, base_ctx, render

        if _has_project_config():
            try:
                ctx = base_ctx(request)
                return render(request, "system/offline.html", ctx)
            except Exception as e:
                logger.error("failed to render offline page", error=str(e))
        return RedirectResponse(url="/onboarding", status_code=303)

    @app.exception_handler(Exception)
    async def _handle_server_error(request: Request, exc: Exception) -> Any:
        import html as _html
        import traceback

        from fastapi.responses import HTMLResponse

        tb = traceback.format_exc()
        req_id = getattr(request.state, "request_id", "")
        logger.error(
            "unhandled exception",
            path=request.url.path,
            method=request.method,
            request_id=req_id,
            error=str(exc),
            traceback=tb,
        )
        safe_path = _html.escape(request.url.path)
        body = (
            "<!doctype html><html><head><title>500 — DEX Studio</title>"
            "<style>body{font-family:monospace;padding:40px;background:#0f1117;color:#e2e8f0}"
            "h2{color:#f87171}pre{background:#1e2533;padding:16px;border-radius:6px;"
            "overflow:auto;font-size:12px;color:#94a3b8}a{color:#60a5fa}</style></head><body>"
            f"<h2>500 — Internal Server Error</h2>"
            f"<p><b>{safe_path}</b> — An unexpected error occurred."
            " Check application logs for details.</p>"
            "<p><a href='/system/logs'>View application logs</a>"
            " &nbsp;·&nbsp; <a href='javascript:history.back()'>Go back</a></p>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=500)


def _add_middlewares(app: FastAPI) -> None:
    """Register session, compression, and HTTP middleware on *app*."""
    secret = os.environ.get("DEX_STUDIO_SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "DEX_STUDIO_SESSION_SECRET environment variable is required. "
            "Set it to a random hex string, e.g.: "
            "DEX_STUDIO_SESSION_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')"
        )
    https_only = os.environ.get("DEX_HTTPS", "").lower() in ("1", "true", "yes")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="dex_session",
        max_age=2592000,  # 30 days — persist across browser restarts
        https_only=https_only,
        same_site="lax",
    )
    app.add_middleware(_SelectiveGZip, minimum_size=1024)

    @app.middleware("http")
    async def _correlation_id(request: Any, call_next: Any) -> Any:
        import uuid

        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    @app.middleware("http")
    async def _security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                # Alpine.js v3 requires unsafe-eval (uses new Function() for expressions)
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            ),
        )
        if https_only:
            # 1-year HSTS, include subdomains — only set when TLS is confirmed active
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
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


def create_app() -> FastAPI:
    """FastAPI application factory — called by uvicorn --factory."""
    from dex_studio.routers import api, data, intelligence, root, secops, system

    app = FastAPI(
        title="DEX Studio",
        description="DataEngineX control plane",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    _register_exception_handlers(app)
    _add_middlewares(app)

    # ── Static files ─────────────────────────────────────────────────────────
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ── Templates (shared singleton) ─────────────────────────────────────────
    templates = make_templates()
    app.state.templates = templates  # type: ignore[attr-defined]

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(root.router)
    app.include_router(data.router, prefix="/data")
    app.include_router(intelligence.router, prefix="/intelligence")
    app.include_router(secops.router, prefix="/secops")
    app.include_router(system.router, prefix="/system")
    app.include_router(api.router, prefix="/api")

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
