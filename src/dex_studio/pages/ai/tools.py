"""AI Tools page — lists configured tools from agent config.

Route: ``/ai/tools``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components import metric_card
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_TOOL_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {
        "name": "used_by",
        "label": "Used By",
        "field": "used_by",
        "align": "left",
    },
]


@ui.page("/ai/tools")
async def ai_tools_page() -> None:
    """Render the AI tools registry."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/tools")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Tools")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                # Collect all unique tools across agents
                tool_agents: dict[str, list[str]] = {}
                for agent_name, agent_cfg in engine.config.ai.agents.items():
                    for tool_name in agent_cfg.tools:
                        tool_agents.setdefault(tool_name, []).append(agent_name)

                ui.label("Tools Registry").classes("section-title")
                metric_card("Registered Tools", len(tool_agents))

                if not tool_agents:
                    empty_state(
                        "No tools registered",
                        icon="build_circle",
                    )
                    return

                rows: list[dict[str, Any]] = [
                    {
                        "name": name,
                        "used_by": ", ".join(agents),
                    }
                    for name, agents in tool_agents.items()
                ]
                data_table(_TOOL_COLUMNS, rows, title="Tools")
