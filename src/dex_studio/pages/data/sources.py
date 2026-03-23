"""Data sources page — list configured data sources.

Route: ``/data/sources``
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
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_SOURCE_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {
        "name": "connector_type",
        "label": "Connector Type",
        "field": "connector_type",
        "align": "left",
    },
]


@ui.page("/data/sources")
async def data_sources_page() -> None:
    """Render the data sources list page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/sources")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Sources")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                try:
                    list_resp = await client.list_sources()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch sources: %s", exc)
                    ui.label("Failed to load data sources.").style(f"color: {COLORS['error']}")
                    return

                sources: list[Any] = list_resp.get("sources", [])
                if not isinstance(sources, list):
                    sources = []

                if not sources:
                    empty_state("No data sources configured", icon="storage")
                    return

                rows: list[dict[str, Any]] = []
                for src in sources:
                    if isinstance(src, dict):
                        rows.append(
                            {
                                "name": src.get("name", "—"),
                                "connector_type": src.get("connector_type", "—"),
                            }
                        )
                    elif isinstance(src, str):
                        rows.append({"name": src, "connector_type": "—"})

                ui.label("Data Sources").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                data_table(_SOURCE_COLUMNS, rows)
