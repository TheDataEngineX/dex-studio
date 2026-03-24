"""Data pipelines page — list and run data pipelines.

Route: ``/data/pipelines``
"""

from __future__ import annotations

import asyncio
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

_PIPELINE_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "source", "label": "Source", "field": "source", "align": "left"},
    {
        "name": "transforms",
        "label": "Transforms",
        "field": "transforms",
        "align": "left",
    },
    {
        "name": "schedule",
        "label": "Schedule",
        "field": "schedule",
        "align": "left",
    },
]


def _run_buttons(engine: DexEngine, rows: list[dict[str, Any]]) -> None:
    """Render a Run button for each pipeline row."""
    ui.label("Actions").classes("section-title mt-4")
    with ui.row().classes("gap-2 flex-wrap"):
        for row in rows:
            pipeline_name: str = row["name"]

            def _make_handler(name: str) -> Any:
                async def _handler() -> None:
                    try:
                        result = await asyncio.to_thread(engine.run_pipeline, name)
                        notify_type: str = "positive" if result.success else "negative"
                        label = "success" if result.success else "failed"
                        ui.notify(
                            f"Pipeline '{name}': {label}",
                            type=notify_type,  # type: ignore[arg-type]
                        )
                    except Exception as exc:
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
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/pipelines")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Pipelines")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                pipelines = engine.config.data.pipelines
                if not pipelines:
                    empty_state("No pipelines configured", icon="account_tree")
                    return

                rows: list[dict[str, Any]] = []
                for name, cfg in pipelines.items():
                    rows.append(
                        {
                            "name": name,
                            "source": cfg.source,
                            "transforms": (", ".join(t.type for t in cfg.transforms) or "\u2014"),
                            "schedule": cfg.schedule or "\u2014",
                        }
                    )

                ui.label("Pipelines").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )
                data_table(_PIPELINE_COLUMNS, rows)
                _run_buttons(engine, rows)
