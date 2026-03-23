"""Lineage page — visualise data lineage events.

Route: ``/lineage``

Drives DEX engine endpoints:
    GET /api/v1/warehouse/lineage/{event_id}  → lineage event lookup
"""

from __future__ import annotations

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.page_layout import page_layout
from dex_studio.theme import COLORS


@ui.page("/lineage")
async def lineage_page() -> None:
    """Render the lineage explorer."""
    with page_layout("Data Lineage", active_route="/lineage") as _content:
        client: DexClient | None = app.storage.general.get("client")
        if client is None:
            ui.label("No connection configured.").style(f"color: {COLORS['error']}")
            return

        ui.label(
            "Look up a lineage event by ID to trace data flow through the medallion pipeline."
        ).classes("text-sm").style(f"color: {COLORS['text_secondary']}")

        # -- Search input --
        event_input = (
            ui.input(
                label="Event ID",
                placeholder="e.g. evt-abc123",
            )
            .classes("w-96")
            .props("outlined dark")
        )

        result_container = ui.column().classes("w-full gap-3 mt-4")

        async def lookup_lineage() -> None:
            event_id = event_input.value
            if not event_id or not event_id.strip():
                return

            result_container.clear()
            with result_container:
                try:
                    data = await client.get_lineage_event(event_id.strip())
                except DexAPIError as exc:
                    ui.label(f"Error: {exc}").style(f"color: {COLORS['error']}")
                    return

                with ui.card().classes("dex-card w-full"):
                    ui.label(f"Lineage: {event_id}").classes("font-semibold text-sm").style(
                        f"color: {COLORS['text_primary']}"
                    )
                    with ui.grid(columns=2).classes("gap-x-6 gap-y-2 mt-3"):
                        for key, value in data.items():
                            ui.label(key).classes("text-xs font-mono").style(
                                f"color: {COLORS['text_muted']}"
                            )
                            ui.label(str(value)).classes("text-sm").style(
                                f"color: {COLORS['text_primary']}"
                            )

                # Placeholder for future graph visualisation
                with ui.card().classes("dex-card w-full mt-2"):
                    ui.label("Lineage Graph").classes("section-title")
                    ui.label(
                        "Graph visualisation will be available when "
                        "PersistentLineage returns full dependency chains."
                    ).classes("text-xs").style(f"color: {COLORS['text_muted']}")

        ui.button(
            "Lookup",
            icon="search",
            on_click=lookup_lineage,
        ).props("color=indigo").classes("mt-2")
