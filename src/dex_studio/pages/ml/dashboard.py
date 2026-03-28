"""ML domain dashboard — overview of experiments and models.

Route: ``/ml``
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


@ui.page("/ml")
async def ml_dashboard_page() -> None:
    """Render the ML domain dashboard."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Overview").classes("section-title")

                experiments_count: str | int = "\u2014"
                if engine.tracker is not None:
                    try:
                        exps = engine.tracker.list_experiments()
                        experiments_count = len(exps)
                    except Exception:
                        experiments_count = "\u2014"

                models_count = len(engine.model_registry.list_models())

                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Experiments", experiments_count)
                    metric_card("Models", models_count)
