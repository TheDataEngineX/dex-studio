"""System components page — detailed component health table.

Route: ``/system/components``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.status_badge import status_badge
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_COMPONENT_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Component", "field": "name", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
    {"name": "count", "label": "Count", "field": "count", "align": "left"},
]


@ui.page("/system/components")
async def system_components_page() -> None:
    """Render the system components detail page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/components")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Components")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                components_data: dict[str, Any] = {}

                try:
                    components_data = await client.components()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch components: %s", exc)
                    ui.label("Failed to load components.").style(f"color: {COLORS['error']}")
                    return

                components_list: list[dict[str, Any]] = components_data.get("components", [])
                if not isinstance(components_list, list):
                    components_list = []

                ui.label("Registered Components").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                if not components_list:
                    empty_state("No components registered", icon="developer_board")
                    return

                # Table view
                rows: list[dict[str, Any]] = [
                    {
                        "name": c.get("name", "—"),
                        "status": c.get("status", "unknown"),
                        "count": str(c.get("count", "—")),
                    }
                    for c in components_list
                ]

                data_table(_COMPONENT_COLUMNS, rows)

                # Card grid with status badges for visual scanning
                ui.label("Status Overview").classes("section-title mt-4")
                with ui.grid(columns=2).classes("gap-3 w-full"):
                    for comp in components_list:
                        name: str = comp.get("name", "—")
                        comp_status: str = comp.get("status", "unknown")
                        count_val = comp.get("count")

                        with (
                            ui.card().classes("dex-card").style("padding: 12px;"),
                            ui.row().classes("items-center justify-between w-full"),
                        ):
                            with ui.column().classes("gap-1"):
                                ui.label(name).classes("text-sm font-semibold").style(
                                    f"color: {COLORS['text_primary']}"
                                )
                                if count_val is not None:
                                    ui.label(f"Count: {count_val}").classes("text-xs").style(
                                        f"color: {COLORS['text_muted']}"
                                    )
                            status_badge(comp_status)
