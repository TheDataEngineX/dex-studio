"""Data quality page — quality gates summary from pipeline config.

Route: ``/data/quality``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_QUALITY_COLUMNS: list[dict[str, Any]] = [
    {
        "name": "pipeline",
        "label": "Pipeline",
        "field": "pipeline",
        "align": "left",
    },
    {
        "name": "completeness",
        "label": "Completeness",
        "field": "completeness",
        "align": "right",
    },
    {
        "name": "uniqueness",
        "label": "Uniqueness",
        "field": "uniqueness",
        "align": "left",
    },
]


@ui.page("/data/quality")
async def data_quality_page() -> None:
    """Render the data quality gates page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/quality")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Quality Gates")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                quality_data: list[dict[str, Any]] = []
                for name, pipe_cfg in engine.config.data.pipelines.items():
                    if pipe_cfg.quality:
                        quality_data.append(
                            {
                                "pipeline": name,
                                "completeness": pipe_cfg.quality.completeness or 0,
                                "uniqueness": (
                                    ", ".join(pipe_cfg.quality.uniqueness)
                                    if pipe_cfg.quality.uniqueness
                                    else "\u2014"
                                ),
                            }
                        )

                ui.label("Quality Gates").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                if not quality_data:
                    empty_state(
                        "No quality checks configured",
                        icon="verified",
                    )
                    return

                data_table(
                    _QUALITY_COLUMNS,
                    quality_data,
                    title="Pipeline Quality Checks",
                )
