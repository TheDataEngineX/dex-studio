"""Data warehouse page — medallion architecture layers and tables.

Route: ``/data/warehouse``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


async def _render_layer(client: DexClient, layer_name: str) -> None:
    """Render a single warehouse layer card with its tables."""
    tables: list[Any] = []
    try:
        tables_resp = await client.warehouse_tables(layer_name)
        raw = tables_resp.get("tables", [])
        tables = raw if isinstance(raw, list) else []
    except DexAPIError as exc:
        _log.warning("Failed to fetch tables for layer %s: %s", layer_name, exc)

    with ui.card().classes("dex-card w-full"):
        ui.label(layer_name.upper()).classes("section-title").style(
            f"color: {COLORS['accent_light']}"
        )
        if tables:
            with ui.column().classes("gap-1 mt-2"):
                for table in tables:
                    table_name = table if isinstance(table, str) else str(table)
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
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/warehouse")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Warehouse")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                try:
                    layers_resp = await client.warehouse_layers()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch warehouse layers: %s", exc)
                    ui.label("Failed to load warehouse layers.").style(f"color: {COLORS['error']}")
                    return

                layers: list[Any] = layers_resp.get("layers", [])
                if not isinstance(layers, list):
                    layers = []

                if not layers:
                    empty_state("No warehouse layers found", icon="warehouse")
                    return

                ui.label("Warehouse Layers").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                for layer in layers:
                    layer_name = layer if isinstance(layer, str) else str(layer)
                    await _render_layer(client, layer_name)
