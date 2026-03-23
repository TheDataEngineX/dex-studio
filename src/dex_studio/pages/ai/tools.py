"""AI Tools page — lists all registered tools from the DEX engine.

Route: ``/ai/tools``

Drives DEX engine endpoints:
    GET /api/v1/ai/tools  → list all registered tools
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import metric_card
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_TOOL_COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "description", "label": "Description", "field": "description", "align": "left"},
]


@ui.page("/ai/tools")
async def ai_tools_page() -> None:
    """Render the AI tools registry."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/tools")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Tools")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                tools: list[dict[str, Any]] = []
                try:
                    tools_resp = await client.list_tools()
                    tools = tools_resp.get("tools", [])
                except DexAPIError as exc:
                    ui.label(f"Error loading tools: {exc}").style(f"color: {COLORS['error']}")
                    return

                ui.label("Tools Registry").classes("section-title")
                metric_card("Registered Tools", len(tools))

                if not tools:
                    empty_state("No tools registered", icon="build_circle")
                    return

                rows = [
                    {
                        "name": t.get("name", "—"),
                        "description": t.get("description", "—"),
                    }
                    for t in tools
                ]
                data_table(_TOOL_COLUMNS, rows, title="Tools")
