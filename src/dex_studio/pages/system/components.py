"""System components page — detailed component health table.

Route: ``/system/components``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.status_badge import status_badge
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_COMPONENT_COLUMNS: list[dict[str, Any]] = [
    {
        "name": "name",
        "label": "Component",
        "field": "name",
        "align": "left",
    },
    {
        "name": "status",
        "label": "Status",
        "field": "status",
        "align": "left",
    },
    {
        "name": "value",
        "label": "Value",
        "field": "value",
        "align": "left",
    },
]


@ui.page("/system/components")
async def system_components_page() -> None:
    """Render the system components detail page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/components")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Components")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                health_data = engine.health()
                components: dict[str, Any] = health_data.get("components", {})

                ui.label("Registered Components").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                if not components:
                    empty_state(
                        "No components registered",
                        icon="developer_board",
                    )
                    return

                rows: list[dict[str, Any]] = []
                for comp_name, comp_val in components.items():
                    comp_status = (
                        "healthy"
                        if comp_val is True or (isinstance(comp_val, int) and comp_val > 0)
                        else "unavailable"
                    )
                    rows.append(
                        {
                            "name": comp_name,
                            "status": comp_status,
                            "value": str(comp_val),
                        }
                    )

                data_table(_COMPONENT_COLUMNS, rows)

                # Card grid with status badges
                ui.label("Status Overview").classes("section-title mt-4")
                with ui.grid(columns=2).classes("gap-3 w-full"):
                    for row in rows:
                        with (
                            ui.card().classes("dex-card").style("padding: 12px;"),
                            ui.row().classes("items-center justify-between w-full"),
                        ):
                            with ui.column().classes("gap-1"):
                                ui.label(row["name"]).classes("text-sm font-semibold").style(
                                    f"color: {COLORS['text_primary']}"
                                )
                                ui.label(f"Value: {row['value']}").classes("text-xs").style(
                                    f"color: {COLORS['text_muted']}"
                                )
                            status_badge(row["status"])
