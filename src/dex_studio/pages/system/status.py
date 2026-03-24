"""System status page — overall health and component summary.

Route: ``/system``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.components.status_badge import status_badge
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/system")
async def system_status_page() -> None:
    """Render the system status page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Status")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                health_data = engine.health()
                health_status: str = health_data.get("status", "unknown")
                components: dict[str, Any] = health_data.get("components", {})

                # -- Health status --
                ui.label("Overall Health").classes("section-title")

                with ui.row().classes("items-center gap-4 flex-wrap"):
                    with ui.card().classes("dex-card").style("padding: 16px; min-width: 180px;"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("monitor_heart", size="sm").style(f"color: {COLORS['accent']}")
                            ui.label("Engine Status").classes("text-sm font-semibold").style(
                                f"color: {COLORS['text_primary']}"
                            )
                        with ui.row().classes("items-center gap-2 mt-2"):
                            status_badge(health_status, size="lg")

                    # Count healthy components (bool True or int > 0)
                    healthy_count = sum(
                        1
                        for v in components.values()
                        if v is True or (isinstance(v, int) and v > 0)
                    )
                    total_count = len(components)
                    metric_card(
                        "Components",
                        f"{healthy_count}/{total_count}",
                    )

                # -- Component summary --
                if components:
                    ui.label("Component Summary").classes("section-title mt-4")
                    with ui.grid(columns=3).classes("gap-3 w-full"):
                        for comp_name, comp_val in components.items():
                            comp_status = (
                                "healthy"
                                if comp_val is True or (isinstance(comp_val, int) and comp_val > 0)
                                else "unavailable"
                            )
                            with (
                                ui.card().classes("dex-card").style("padding: 12px;"),
                                ui.row().classes("items-center justify-between"),
                            ):
                                ui.label(comp_name).classes("text-sm font-mono").style(
                                    f"color: {COLORS['text_primary']}"
                                )
                                status_badge(comp_status)
                else:
                    ui.label("No component data available.").classes("text-sm").style(
                        f"color: {COLORS['text_muted']}"
                    )
