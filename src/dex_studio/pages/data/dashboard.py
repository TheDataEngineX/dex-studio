"""Data domain dashboard — overview of pipelines, sources, and quality.

Route: ``/data``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


async def _safe_fetch(client: DexClient, method: str) -> dict[str, Any]:
    """Call a client method by name, returning empty dict on error."""
    try:
        result: dict[str, Any] = await getattr(client, method)()
        return result
    except DexAPIError as exc:
        _log.warning("Failed to fetch %s: %s", method, exc)
        return {}


def _pipeline_count(data: dict[str, Any]) -> str | int:
    """Extract pipeline count from list response."""
    pipelines_list = data.get("pipelines", [])
    return len(pipelines_list) if isinstance(pipelines_list, list) else "—"


def _source_count(data: dict[str, Any]) -> str | int:
    """Extract source count from list response."""
    sources_list = data.get("sources", [])
    return len(sources_list) if isinstance(sources_list, list) else "—"


def _pass_rate_display(data: dict[str, Any]) -> tuple[str, str]:
    """Return (display_string, color) for pass rate from quality summary."""
    raw_rate = data.get("overall_pass_rate", data.get("pass_rate"))
    if isinstance(raw_rate, (int, float)):
        color = COLORS["success"] if raw_rate >= 0.8 else COLORS["warning"]
        return f"{raw_rate:.0%}", color
    return "—", COLORS["text_muted"]


@ui.page("/data")
async def data_dashboard_page() -> None:
    """Render the data domain dashboard."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Overview").classes("section-title")

                pipelines_data = await _safe_fetch(client, "list_pipelines")
                sources_data = await _safe_fetch(client, "list_sources")
                quality_data = await _safe_fetch(client, "data_quality_summary")

                pass_rate_str, pass_rate_color = _pass_rate_display(quality_data)

                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Pipelines", _pipeline_count(pipelines_data))
                    metric_card("Sources", _source_count(sources_data))
                    metric_card("Quality Pass Rate", pass_rate_str, color=pass_rate_color)
