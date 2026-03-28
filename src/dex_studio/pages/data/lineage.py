"""Data lineage page — lineage event log with detail drill-down.

Route: ``/data/lineage``
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

_LINEAGE_COLUMNS: list[dict[str, Any]] = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {
        "name": "source",
        "label": "Source",
        "field": "source",
        "align": "left",
    },
    {
        "name": "destination",
        "label": "Destination",
        "field": "destination",
        "align": "left",
    },
    {
        "name": "operation",
        "label": "Operation",
        "field": "operation",
        "align": "left",
    },
    {
        "name": "layer",
        "label": "Layer",
        "field": "layer",
        "align": "left",
    },
    {
        "name": "timestamp",
        "label": "Timestamp",
        "field": "timestamp",
        "align": "left",
    },
]


@ui.page("/data/lineage")
async def data_lineage_page() -> None:
    """Render the data lineage page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/lineage")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Lineage")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                events = engine.lineage.all_events
                if not events:
                    empty_state("No lineage events recorded", icon="timeline")
                    return

                rows: list[dict[str, Any]] = [
                    {
                        "id": evt.event_id,
                        "source": evt.source or "\u2014",
                        "destination": evt.destination or "\u2014",
                        "operation": evt.operation or "\u2014",
                        "layer": evt.layer or "\u2014",
                        "timestamp": evt.timestamp.isoformat(),
                    }
                    for evt in events
                ]

                ui.label("Lineage Events").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                table = data_table(_LINEAGE_COLUMNS, rows, row_key="id")
                detail_container = ui.column().classes("gap-2 w-full mt-4")

                def _on_row_click(e: Any) -> None:
                    event_id: str = e.args.get("id", "") if isinstance(e.args, dict) else ""
                    if not event_id or event_id == "\u2014":
                        return
                    evt = engine.lineage.get_event(event_id)
                    detail_container.clear()
                    if evt is None:
                        with detail_container:
                            ui.label(f"Event {event_id} not found").style(
                                f"color: {COLORS['error']}"
                            )
                        return
                    with detail_container:
                        ui.label(f"Event Detail \u2014 {event_id}").classes(
                            "text-sm font-semibold"
                        ).style(f"color: {COLORS['text_primary']}")
                        with ui.card().classes("dex-card w-full"):
                            detail = evt.to_dict()
                            for key, val in detail.items():
                                with ui.row().classes("gap-2"):
                                    ui.label(str(key)).classes("text-xs font-mono").style(
                                        f"color: {COLORS['text_dim']}; min-width: 120px;"
                                    )
                                    ui.label(str(val)).classes("text-sm").style(
                                        f"color: {COLORS['text_muted']}"
                                    )

                table.on("rowClick", _on_row_click)
