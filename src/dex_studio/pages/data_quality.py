"""Data Quality page — medallion layer quality scores and drill-down.

Route: ``/quality``

Drives DEX engine endpoints:
    GET /api/v1/data/quality          → aggregate summary
    GET /api/v1/data/quality/{layer}  → per-layer detail
    GET /api/v1/data/sources          → registered data sources
    GET /api/v1/warehouse/layers      → medallion layer config
"""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import metric_card, page_layout
from dex_studio.theme import COLORS

_LAYERS = ["bronze", "silver", "gold"]

_LAYER_ICONS: dict[str, str] = {
    "bronze": "filter_1",
    "silver": "filter_2",
    "gold": "filter_3",
}

_LAYER_COLORS: dict[str, str] = {
    "bronze": "#cd7f32",
    "silver": "#c0c0c0",
    "gold": "#ffd700",
}

_LAYER_DETAIL_KEYS = (
    "purpose",
    "format",
    "quality_threshold",
    "retention_days",
)


def _render_summary_metrics(summary: dict[str, Any]) -> None:
    """Render the aggregate quality metrics row."""
    ui.label("Aggregate Metrics").classes("section-title")
    with ui.row().classes("gap-4 flex-wrap"):
        total = summary.get("total_evaluations", 0)
        pass_rate = summary.get("pass_rate", 0)
        avg = summary.get("average_score", 0)

        metric_card("Evaluations", total, icon="assessment")
        _pass_color = (
            COLORS["success"]
            if (isinstance(pass_rate, (int, float)) and pass_rate >= 0.75)
            else COLORS["warning"]
        )
        metric_card(
            "Pass Rate",
            f"{pass_rate:.0%}" if isinstance(pass_rate, float) else str(pass_rate),
            icon="check_circle",
            color=_pass_color,
        )
        metric_card(
            "Avg Score",
            f"{avg:.1f}" if isinstance(avg, float) else str(avg),
            icon="speed",
        )


def _render_layer_card(layer_cfg: dict[str, Any]) -> None:
    """Render a single medallion layer config card."""
    name = layer_cfg.get("name", "")
    color = _LAYER_COLORS.get(name, COLORS["accent"])
    with ui.card().classes("dex-card").style(f"border-color: {color}"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(_LAYER_ICONS.get(name, "layers"), size="xs").style(f"color: {color}")
            ui.label(name.upper()).classes("font-bold text-sm").style(f"color: {color}")
        with ui.grid(columns=2).classes("gap-x-4 gap-y-1 mt-2"):
            for key in _LAYER_DETAIL_KEYS:
                ui.label(key).classes("text-xs font-mono").style(f"color: {COLORS['text_muted']}")
                ui.label(str(layer_cfg.get(key, "—"))).classes("text-xs").style(
                    f"color: {COLORS['text_primary']}"
                )


def _render_layer_detail(detail: dict[str, Any]) -> None:
    """Render quality detail for a single layer (latest + history)."""
    latest = detail.get("latest")
    if latest:
        with ui.card().classes("dex-card w-full"):
            ui.label("Latest Evaluation").classes("font-semibold text-sm").style(
                f"color: {COLORS['text_primary']}"
            )
            with ui.grid(columns=2).classes("gap-x-4 gap-y-1 mt-2"):
                for k, v in latest.items():
                    ui.label(k).classes("text-xs font-mono").style(f"color: {COLORS['text_muted']}")
                    ui.label(str(v)).classes("text-xs").style(f"color: {COLORS['text_primary']}")
    else:
        ui.label("No evaluations recorded yet.").style(f"color: {COLORS['text_muted']}")

    history = detail.get("history", [])
    if history:
        ui.label("History").classes("section-title mt-3")
        columns = [{"name": k, "label": k, "field": k, "align": "left"} for k in history[0]]
        ui.table(columns=columns, rows=history).classes("w-full")


async def _render_sources(client: DexClient) -> None:
    """Render the registered data sources table."""
    ui.label("Registered Sources").classes("section-title mt-6")
    try:
        sources_resp = await client.data_sources()
        items: list[dict[str, Any]] = sources_resp.get("items", [])
        if items:
            columns = [
                {"name": "name", "label": "Name", "field": "name", "align": "left"},
                {"name": "type", "label": "Type", "field": "type", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
            ]
            ui.table(columns=columns, rows=items).classes("w-full")
        else:
            ui.label("No data sources registered.").style(f"color: {COLORS['text_muted']}")
    except DexAPIError as exc:
        ui.label(f"Failed to load sources: {exc}").style(f"color: {COLORS['error']}")


@ui.page("/quality")
async def data_quality_page() -> None:
    """Render the data quality dashboard."""
    with page_layout("Data Quality", active_route="/quality") as _content:
        client: DexClient | None = app.storage.general.get("client")
        if client is None:
            ui.label("No connection configured.").style(f"color: {COLORS['error']}")
            return

        # -- Summary --
        try:
            summary = await client.data_quality_summary()
        except DexAPIError as exc:
            ui.label(f"Failed to load quality summary: {exc}").style(f"color: {COLORS['error']}")
            summary = {}

        _render_summary_metrics(summary)

        # -- Warehouse layers --
        try:
            layers_resp = await client.warehouse_layers()
            layers_list: list[dict[str, Any]] = layers_resp.get("layers", [])
        except DexAPIError:
            layers_list = []

        if layers_list:
            ui.label("Medallion Layers").classes("section-title mt-6")
            with ui.row().classes("gap-4 flex-wrap"):
                for layer_cfg in layers_list:
                    _render_layer_card(layer_cfg)

        # -- Per-layer quality detail --
        ui.label("Layer Quality Detail").classes("section-title mt-6")
        layer_tabs = ui.tabs().classes("w-full")
        with layer_tabs:
            tabs = {layer: ui.tab(layer.upper()) for layer in _LAYERS}

        panels = ui.tab_panels(layer_tabs).classes("w-full")
        with panels:
            for layer in _LAYERS:
                with ui.tab_panel(tabs[layer]):
                    try:
                        detail = await client.data_quality_layer(layer)
                    except DexAPIError:
                        detail = {}
                    _render_layer_detail(detail)

        # -- Sources --
        await _render_sources(client)
