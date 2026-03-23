"""System settings page — current config display and connection test.

Route: ``/system/settings``
"""

from __future__ import annotations

import logging

from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.status_badge import status_badge
from dex_studio.config import StudioConfig
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _mask_token(token: str | None) -> str:
    """Mask all but the first 4 chars of a token."""
    if not token:
        return "—"
    if len(token) <= 4:
        return "****"
    return token[:4] + "*" * (len(token) - 4)


@ui.page("/system/settings")
async def system_settings_page() -> None:
    """Render the system settings page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")
    config: StudioConfig | None = app.storage.general.get("config")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/settings")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Settings")
            with ui.column().classes("p-6 gap-4 w-full"):
                ui.label("Studio Configuration").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                if config is None:
                    ui.label("Configuration not available.").style(f"color: {COLORS['error']}")
                    return

                # -- Config display --
                with ui.card().classes("dex-card").style("padding: 20px; max-width: 600px;"):
                    ui.label("Connection").classes("section-title")
                    with ui.grid(columns=2).classes("gap-x-8 gap-y-3 mt-2"):
                        _config_row("API URL", config.api_url)
                        _config_row("API Token", _mask_token(config.api_token))
                        _config_row("Timeout", f"{config.timeout}s")
                        _config_row("Theme", config.theme)
                        _config_row("Poll Interval", f"{config.poll_interval}s")
                        _config_row("Host", config.host)
                        _config_row("Port", str(config.port))

                # -- Connection test --
                ui.label("Connection Test").classes("section-title mt-2")
                result_label = (
                    ui.label("").classes("text-sm").style(f"color: {COLORS['text_muted']}")
                )
                status_container = ui.row().classes("items-center gap-2")

                async def _test_connection() -> None:
                    result_label.set_text("Testing connection…")
                    status_container.clear()

                    if client is None:
                        result_label.set_text("No client available.")
                        return

                    alive = await client.ping()
                    if alive:
                        result_label.set_text("Connection successful.")
                        with status_container:
                            status_badge("alive")
                    else:
                        result_label.set_text("Connection failed — engine unreachable.")
                        with status_container:
                            status_badge("error")

                ui.button("Test Connection", icon="lan", on_click=_test_connection).props(
                    "flat"
                ).style(f"color: {COLORS['accent']}")


def _config_row(label: str, value: str) -> None:
    """Render a label/value pair inside a grid."""
    ui.label(label).classes("text-sm").style(f"color: {COLORS['text_muted']}")
    ui.label(value).classes("text-sm font-mono").style(f"color: {COLORS['text_primary']}")
