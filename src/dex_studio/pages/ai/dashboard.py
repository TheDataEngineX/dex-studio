"""AI domain dashboard — overview metrics for agents and tools.

Route: ``/ai``
"""

from __future__ import annotations

import logging

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components import metric_card
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/ai")
async def ai_dashboard_page() -> None:
    """Render the AI domain dashboard."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                agent_configs = engine.config.ai.agents
                live_agents = engine.agents

                ui.label("AI Overview").classes("section-title")
                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Agents", len(agent_configs))
                    tool_count = 0
                    for cfg in agent_configs.values():
                        if cfg and cfg.tools:
                            tool_count += len(cfg.tools)
                    metric_card("Tools", tool_count)

                if agent_configs:
                    ui.label("Registered Agents").classes("section-title mt-4")
                    with (
                        ui.card().classes("dex-card w-full"),
                        ui.grid(columns=2).classes("gap-x-8 gap-y-2"),
                    ):
                        for name in agent_configs:
                            status = "available" if name in live_agents else "unavailable"
                            ui.label(name).classes("text-xs font-mono").style(
                                f"color: {COLORS['text_muted']}"
                            )
                            ui.label(status).classes("text-sm").style(
                                f"color: {COLORS['text_primary']}"
                            )
