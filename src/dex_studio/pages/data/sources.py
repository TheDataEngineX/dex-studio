"""Data sources page — list configured data sources.

Route: ``/data/sources``
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
from dex_studio.engine import DexEngine
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
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/sources")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Sources")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                sources_config = engine.config.data.sources
                if not sources_config:
                    empty_state("No data sources configured", icon="storage")
                    return

                rows: list[dict[str, Any]] = []
                for name, src in sources_config.items():
                    rows.append(
                        {
                            "name": name,
                            "connector_type": src.type,
                        }
                    )

                ui.label("Data Sources").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                data_table(_SOURCE_COLUMNS, rows)
