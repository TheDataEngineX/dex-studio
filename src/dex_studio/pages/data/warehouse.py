"""Data warehouse page — medallion architecture layers and tables.

Route: ``/data/warehouse``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _render_layer(tables: list[dict[str, Any]], layer_name: str) -> None:
    """Render a single warehouse layer card with its tables."""
    with ui.card().classes("dex-card w-full"):
        ui.label(layer_name.upper()).classes("section-title").style(
            f"color: {COLORS['accent_light']}"
        )
        if tables:
            with ui.column().classes("gap-1 mt-2"):
                for table in tables:
                    table_name = table.get("name", "\u2014")
                    with ui.row().classes("items-center gap-2").style("padding: 4px 0;"):
                        ui.icon("table_chart", size="xs").style(f"color: {COLORS['text_dim']}")
                        ui.label(table_name).classes("text-sm font-mono").style(
                            f"color: {COLORS['text_muted']}"
                        )
        else:
            ui.label("No tables in this layer.").classes("text-xs").style(
                f"color: {COLORS['text_dim']}"
            )


@ui.page("/data/warehouse")
async def data_warehouse_page() -> None:
    """Render the data warehouse layers page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/warehouse")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Warehouse")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                layers = engine.warehouse_layers()
                if not layers:
                    empty_state("No warehouse layers found", icon="warehouse")
                    return

                ui.label("Warehouse Layers").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                for layer in layers:
                    layer_name: str = layer.get("name", "")
                    tables = engine.warehouse_tables(layer_name)
                    _render_layer(tables, layer_name)
