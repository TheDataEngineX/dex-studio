"""System status page — overall health and component summary.

Route: ``/system``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.components.status_badge import status_badge
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/system")
async def system_status_page() -> None:
    """Render the system status page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Status")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                health_data: dict[str, Any] = {}
                components_data: dict[str, Any] = {}

                try:
                    health_data = await client.health()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch health: %s", exc)

                try:
                    components_data = await client.components()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch components: %s", exc)

                # -- Health status --
                ui.label("Overall Health").classes("section-title")
                health_status: str = health_data.get("status", "unknown")

                with ui.row().classes("items-center gap-4 flex-wrap"):
                    with ui.card().classes("dex-card").style("padding: 16px; min-width: 180px;"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("monitor_heart", size="sm").style(f"color: {COLORS['accent']}")
                            ui.label("Engine Status").classes("text-sm font-semibold").style(
                                f"color: {COLORS['text_primary']}"
                            )
                        with ui.row().classes("items-center gap-2 mt-2"):
                            status_badge(health_status, size="lg")

                    components_list: list[dict[str, Any]] = components_data.get("components", [])
                    if not isinstance(components_list, list):
                        components_list = []

                    healthy_count = sum(
                        1
                        for c in components_list
                        if c.get("status", "").lower() in {"healthy", "alive", "ready"}
                    )
                    total_count = len(components_list)

                    metric_card("Components", f"{healthy_count}/{total_count}")

                # -- Component summary --
                if components_list:
                    ui.label("Component Summary").classes("section-title mt-4")
                    with ui.grid(columns=3).classes("gap-3 w-full"):
                        for comp in components_list:
                            name: str = comp.get("name", "—")
                            comp_status: str = comp.get("status", "unknown")
                            with ui.card().classes("dex-card").style("padding: 12px;"):  # noqa: SIM117
                                with ui.row().classes("items-center justify-between"):
                                    ui.label(name).classes("text-sm font-mono").style(
                                        f"color: {COLORS['text_primary']}"
                                    )
                                    status_badge(comp_status)
                else:
                    ui.label("No component data available.").classes("text-sm").style(
                        f"color: {COLORS['text_muted']}"
                    )
