"""DEX Studio — FastAPI application factory."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dex_studio.utils import fmt_bytes, fmt_cron, fmt_ts, status_color

logger = structlog.getLogger()

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


def create_app() -> FastAPI:
    """FastAPI application factory — called by uvicorn --factory."""
    from dex_studio.routers import ai, data, ml, root, system

    app = FastAPI(
        title="DEX Studio",
        description="DataEngineX control plane",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # ── Session middleware ────────────────────────────────────────────────────
    secret = os.environ.get("DEX_STUDIO_SESSION_SECRET") or _session_secret()
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="dex_session")

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
    app.include_router(system.router, prefix="/system")

    logger.info("DEX Studio started", port=7860)
    return app


# ── Template helpers used across routers ────────────────────────────────────


def get_templates(app: Any) -> Jinja2Templates:
    return app.state.templates  # type: ignore[no-any-return]
