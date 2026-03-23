"""Data lineage page — lineage event log with detail drill-down.

Route: ``/data/lineage``
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

_LINEAGE_COLUMNS: list[dict[str, Any]] = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
    {"name": "target", "label": "Target", "field": "target", "align": "left"},
    {"name": "operation", "label": "Operation", "field": "operation", "align": "left"},
    {"name": "timestamp", "label": "Timestamp", "field": "timestamp", "align": "left"},
]


def _event_to_row(evt: Any) -> dict[str, Any] | None:
    """Convert a lineage event dict to a table row, or None if not a dict."""
    if not isinstance(evt, dict):
        return None
    return {
        "id": evt.get("id", "—"),
        "source": evt.get("source", "—"),
        "target": evt.get("target", "—"),
        "operation": evt.get("operation", "—"),
        "timestamp": evt.get("timestamp", "—"),
    }


def _render_detail(detail: dict[str, Any], event_id: str, container: ui.column) -> None:
    """Populate the detail container with lineage event fields."""
    container.clear()
    with container:
        ui.label(f"Event Detail — {event_id}").classes("text-sm font-semibold").style(
            f"color: {COLORS['text_primary']}"
        )
        with ui.card().classes("dex-card w-full"):
            for key, val in detail.items():
                with ui.row().classes("gap-2"):
                    ui.label(str(key)).classes("text-xs font-mono").style(
                        f"color: {COLORS['text_dim']}; min-width: 120px;"
                    )
                    ui.label(str(val)).classes("text-sm").style(f"color: {COLORS['text_muted']}")


@ui.page("/data/lineage")
async def data_lineage_page() -> None:
    """Render the data lineage page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/lineage")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Lineage")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                try:
                    list_resp = await client.list_lineage()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch lineage events: %s", exc)
                    ui.label("Failed to load lineage events.").style(f"color: {COLORS['error']}")
                    return

                events: list[Any] = list_resp.get("events", [])
                if not isinstance(events, list):
                    events = []

                if not events:
                    empty_state("No lineage events recorded", icon="timeline")
                    return

                rows = [r for evt in events if (r := _event_to_row(evt)) is not None]

                ui.label("Lineage Events").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                table = data_table(_LINEAGE_COLUMNS, rows, row_key="id")
                detail_container = ui.column().classes("gap-2 w-full mt-4")

                async def _on_row_click(e: Any) -> None:
                    event_id: str = e.args.get("id", "") if isinstance(e.args, dict) else ""
                    if not event_id or event_id == "—":
                        return
                    detail_container.clear()
                    try:
                        detail = await client.get_lineage_event(event_id)
                    except DexAPIError as exc:
                        _log.warning("Failed to fetch lineage event %s: %s", event_id, exc)
                        with detail_container:
                            ui.label(f"Failed to load event {event_id}").style(
                                f"color: {COLORS['error']}"
                            )
                        return
                    _render_detail(detail, event_id, detail_container)

                table.on("rowClick", _on_row_click)
