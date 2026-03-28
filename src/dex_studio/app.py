"""DEX Studio — NiceGUI application entry point.

Creates the NiceGUI app on top of the DEX FastAPI app (via ui.run_with),
registers all pages, and launches.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

from nicegui import app, ui

from dex_studio.config import StudioConfig, load_config
from dex_studio.engine import DexEngine

_log = logging.getLogger(__name__)

__all__ = ["start", "get_engine", "get_studio_config", "get_theme"]

# Module-level store for non-serializable singletons.
# NiceGUI's app.storage.general is persisted to disk as JSON — DexEngine
# and StudioConfig are not JSON-serializable, so they must live here.
_state: dict[str, object] = {}


def get_engine() -> DexEngine | None:
    """Return the active DexEngine, or None if not yet initialised."""
    return _state.get("engine")  # type: ignore[return-value]


def get_studio_config() -> StudioConfig | None:
    """Return the active StudioConfig, or None if not yet initialised."""
    return _state.get("config")  # type: ignore[return-value]


def get_theme() -> str:
    """Return the active theme name ('dark' or 'light')."""
    cfg = get_studio_config()
    return cfg.theme if cfg is not None else "dark"


def _register_pages() -> None:
    """Import all page modules to register their routes."""
    import importlib

    from dex_studio.pages import project_hub  # noqa: F401

    _optional_imports = [
        "dex_studio.pages.data.dashboard",
        "dex_studio.pages.data.pipelines",
        "dex_studio.pages.data.sources",
        "dex_studio.pages.data.warehouse",
        "dex_studio.pages.data.quality",
        "dex_studio.pages.data.lineage",
        "dex_studio.pages.ml.dashboard",
        "dex_studio.pages.ml.experiments",
        "dex_studio.pages.ml.models",
        "dex_studio.pages.ml.predictions",
        "dex_studio.pages.ml.features",
        "dex_studio.pages.ml.drift",
        "dex_studio.pages.ai.dashboard",
        "dex_studio.pages.ai.agents",
        "dex_studio.pages.ai.tools",
        "dex_studio.pages.ai.collections",
        "dex_studio.pages.ai.retrieval",
        "dex_studio.pages.system.status",
        "dex_studio.pages.system.components",
        "dex_studio.pages.system.metrics",
        "dex_studio.pages.system.logs",
        "dex_studio.pages.system.traces",
        "dex_studio.pages.system.settings",
        "dex_studio.pages.system.connection",
    ]
    for mod in _optional_imports:
        with contextlib.suppress(ImportError):
            importlib.import_module(mod)


def start(
    config_path: Path | None = None,
    studio_config: StudioConfig | None = None,
    *,
    config: StudioConfig | None = None,
) -> None:
    """Launch DEX Studio.

    Parameters
    ----------
    config_path:
        Path to a dex YAML config file. DexEngine loads and validates it.
        Omit when connecting to a remote engine via ``config.api_url``.
    studio_config:
        UI-level preferences (positional form, kept for back-compat).
    config:
        UI-level preferences (keyword-only form; takes precedence over
        ``studio_config`` when both are supplied).
    """
    ui_cfg = config or studio_config or load_config()

    if config_path is not None:
        # Local mode: load DexEngine from config file
        resolved = config_path.resolve()
        if not resolved.exists():
            sys.stderr.write(f"Config not found: {resolved}\n")
            sys.stderr.write("Usage: dex-studio <path-to-config.yaml>\n")
            sys.exit(1)

        engine = DexEngine(resolved)
        _state["engine"] = engine
        _state["config"] = ui_cfg

        from dataenginex.api.factory import create_app

        dex_api = create_app(engine.config, skip_lifespan=True)
        dex_api.state.config = engine.config
        dex_api.state.pipeline_runner = engine.pipeline_runner
        dex_api.state.lineage = engine.lineage
        dex_api.state.tracker = engine.tracker
        dex_api.state.feature_store = engine.feature_store
        dex_api.state.model_registry = engine.model_registry
        dex_api.state.serving_engine = engine.serving_engine
        dex_api.state.llm = engine.llm
        dex_api.state.agents = engine.agents

        app.on_shutdown(engine.close)
        _register_pages()

        import fastapi
        import uvicorn

        # NiceGUI needs to own the root app — mounting DEX API under /api
        # prevents the DEX root router from shadowing NiceGUI's @ui.page("/").
        nicegui_app = fastapi.FastAPI()
        nicegui_app.mount("/api", dex_api)

        ui.run_with(
            nicegui_app,
            title="DEX Studio",
            storage_secret="dex-studio-secret",
            dark=ui_cfg.theme == "dark",
        )

        uvicorn.run(nicegui_app, host=ui_cfg.host, port=ui_cfg.port)
        return

    # HTTP / hub mode: no local engine
    _state["config"] = ui_cfg
    _register_pages()

    import fastapi
    import uvicorn

    http_app = fastapi.FastAPI()
    ui.run_with(
        http_app,
        title="DEX Studio",
        storage_secret="dex-studio-secret",
        dark=ui_cfg.theme == "dark",
    )
    uvicorn.run(http_app, host=ui_cfg.host, port=ui_cfg.port)


def _check_native_support() -> bool:
    """Return True if pywebview can find a usable GUI backend."""
    try:
        from webview.guilib import initialize

        initialize()
        return True  # noqa: TRY300
    except Exception:  # noqa: BLE001
        _log.warning("pywebview cannot find GTK or QT — falling back to browser mode.")
        return False
