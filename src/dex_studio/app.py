"""DEX Studio — NiceGUI application entry point.

Creates the NiceGUI app, wires up the shared ``DexClient``, registers
all pages, and starts the native-mode window (or falls back to browser
when pywebview is unavailable).
"""

from __future__ import annotations

import contextlib
import logging

from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.config import StudioConfig, load_config

_log = logging.getLogger(__name__)

__all__ = ["start"]


def _register_pages() -> None:
    """Import all page modules to register their routes."""
    import importlib

    from dex_studio.pages import project_hub  # noqa: F401

    # Domain pages — imported when available
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


def start(config: StudioConfig | None = None) -> None:
    """Launch DEX Studio in native mode.

    Parameters
    ----------
    config:
        Optional pre-built config.  Falls back to ``load_config()``.
    """
    cfg = config or load_config()

    # Store config and client on the NiceGUI app for access in pages
    client = DexClient(config=cfg)
    app.storage.general["config"] = cfg
    app.storage.general["client"] = client

    async def on_startup() -> None:
        await client.connect()

    async def on_shutdown() -> None:
        await client.close()

    app.on_startup(on_startup)
    app.on_shutdown(on_shutdown)

    _register_pages()

    use_native = cfg.native_mode
    if use_native:
        use_native = _check_native_support()

    run_kwargs: dict[str, object] = {
        "title": "DEX Studio",
        "host": cfg.host,
        "port": cfg.port,
        "native": use_native,
        "reload": False,
        "show": not use_native,
        "dark": cfg.theme == "dark",
        "storage_secret": "dex-studio-secret",
    }
    if use_native:
        run_kwargs["window_size"] = (cfg.window_width, cfg.window_height)

    ui.run(**run_kwargs)  # type: ignore[arg-type]


def _check_native_support() -> bool:
    """Return ``True`` if pywebview can find a usable GUI backend."""
    try:
        from webview.guilib import initialize  # noqa: WPS433

        initialize()
        return True  # noqa: TRY300
    except Exception:  # noqa: BLE001
        _log.warning(
            "pywebview cannot find GTK or QT — falling back to browser mode. "
            "Install PyGObject (GTK) or PyQt6/qtpy (QT) for native window support.",
        )
        return False
