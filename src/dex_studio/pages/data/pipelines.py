"""Data pipelines page — list and run data pipelines.

Route: ``/data/pipelines``
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

_PIPELINE_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
    {"name": "transforms", "label": "Transforms", "field": "transforms", "align": "left"},
    {"name": "schedule", "label": "Schedule", "field": "schedule", "align": "left"},
]


def _transforms_display(transforms_raw: Any) -> str:
    """Format the transforms field for display."""
    if isinstance(transforms_raw, list):
        return ", ".join(str(t) for t in transforms_raw) or "—"
    return str(transforms_raw) if transforms_raw else "—"


async def _build_pipeline_rows(client: DexClient, names: list[str]) -> list[dict[str, Any]]:
    """Fetch detail for each pipeline name and build table rows."""
    rows: list[dict[str, Any]] = []
    for name in names:
        detail: dict[str, Any] = {}
        try:
            detail = await client.get_pipeline(name)
        except DexAPIError as exc:
            _log.warning("Failed to fetch pipeline %s: %s", name, exc)
        rows.append(
            {
                "name": name,
                "source": detail.get("source", "—"),
                "transforms": _transforms_display(detail.get("transforms", [])),
                "schedule": detail.get("schedule", "—"),
            }
        )
    return rows


def _run_buttons(client: DexClient, rows: list[dict[str, Any]]) -> None:
    """Render a Run button for each pipeline row."""
    ui.label("Actions").classes("section-title mt-4")
    with ui.row().classes("gap-2 flex-wrap"):
        for row in rows:
            pipeline_name: str = row["name"]

            def _make_handler(name: str) -> Any:
                async def _handler() -> None:
                    try:
                        result = await client.run_pipeline(name)
                        ui.notify(
                            f"Pipeline '{name}' triggered: {result.get('status', 'ok')}",
                            type="positive",
                        )
                    except DexAPIError as exc:
                        _log.error("Failed to run pipeline %s: %s", name, exc)
                        ui.notify(f"Failed to run '{name}'", type="negative")

                return _handler

            ui.button(
                f"Run {pipeline_name}",
                icon="play_arrow",
                on_click=_make_handler(pipeline_name),
            ).props("flat").style(f"color: {COLORS['accent']}")


@ui.page("/data/pipelines")
async def data_pipelines_page() -> None:
    """Render the data pipelines list page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/pipelines")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Pipelines")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                try:
                    list_resp = await client.list_pipelines()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch pipelines: %s", exc)
                    ui.label("Failed to load pipelines.").style(f"color: {COLORS['error']}")
                    return

                pipeline_names: list[str] = list_resp.get("pipelines", [])
                if not isinstance(pipeline_names, list):
                    pipeline_names = []

                if not pipeline_names:
                    empty_state("No pipelines configured", icon="account_tree")
                    return

                rows = await _build_pipeline_rows(client, pipeline_names)

                ui.label("Pipelines").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                data_table(_PIPELINE_COLUMNS, rows)
                _run_buttons(client, rows)
