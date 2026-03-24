"""Data domain dashboard — overview of pipelines, sources, and quality.

Route: ``/data``
"""

from __future__ import annotations

import logging

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/data")
async def data_dashboard_page() -> None:
    """Render the data domain dashboard."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Overview").classes("section-title")

                pipeline_count = len(engine.config.data.pipelines)
                source_count = len(engine.config.data.sources)

                # Count pipelines with quality checks configured
                quality_count = sum(1 for p in engine.config.data.pipelines.values() if p.quality)

                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Pipelines", pipeline_count)
                    metric_card("Sources", source_count)
                    metric_card("Quality Checks", quality_count)
