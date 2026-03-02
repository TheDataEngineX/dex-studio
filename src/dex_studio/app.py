"""DEX Studio — NiceGUI application entry point.

Creates the NiceGUI app, wires up the shared ``DexClient``, registers
all pages, and starts the native-mode window (or falls back to browser
when pywebview is unavailable).
"""

from __future__ import annotations

import logging

from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.config import StudioConfig, load_config

_log = logging.getLogger(__name__)

__all__ = ["start"]


def _register_pages() -> None:
    """Import page modules so their ``@ui.page`` decorators register routes."""
    from dex_studio.pages import (
        data_quality,  # noqa: F401
        health,  # noqa: F401
        lineage,  # noqa: F401
        ml_models,  # noqa: F401
        overview,  # noqa: F401
        settings,  # noqa: F401
    )


def start(config: StudioConfig | None = None) -> None:
    """Launch DEX Studio in native mode.

    Parameters
    ----------
    config:
        Optional pre-built config.  Falls back to ``load_config()``.
    """
    cfg = config or load_config()

    # Store config and client on the NiceGUI app for access in pages
    app.storage.general["config"] = cfg
    client = DexClient(config=cfg)

    async def on_startup() -> None:
        await client.connect()
        app.storage.general["client"] = client

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
        "native": use_native,
        "reload": False,
        "show": True,
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
