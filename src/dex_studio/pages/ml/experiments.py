"""ML experiments page — list and create experiments.

Route: ``/ml/experiments``
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

_EXPERIMENT_COLUMNS: list[dict[str, Any]] = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
]


@ui.page("/ml/experiments")
async def ml_experiments_page() -> None:
    """Render the ML experiments page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/experiments")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Experiments")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                if engine.tracker is None:
                    ui.label("ML tracker unavailable.").style(f"color: {COLORS['warning']}")
                    return

                # -- Create experiment --
                ui.label("Create Experiment").classes("section-title")
                with ui.row().classes("items-end gap-3"):
                    new_name_input = (
                        ui.input(
                            label="Experiment Name",
                            placeholder="e.g. churn_v2",
                        )
                        .classes("w-64")
                        .props("outlined dark")
                    )
                    create_result = (
                        ui.label("").classes("text-xs").style(f"color: {COLORS['text_muted']}")
                    )

                experiments_container = ui.column().classes("w-full gap-2 mt-4")

                def refresh_experiments() -> None:
                    experiments_container.clear()
                    with experiments_container:
                        experiments: list[dict[str, Any]] = engine.tracker.list_experiments()

                        ui.label("Experiments").classes("section-title")
                        if not experiments:
                            empty_state(
                                "No experiments found",
                                icon="science",
                            )
                            return

                        rows = [
                            {
                                "id": e.get("id", "\u2014"),
                                "name": e.get("name", "\u2014"),
                            }
                            for e in experiments
                        ]
                        data_table(
                            _EXPERIMENT_COLUMNS,
                            rows,
                            title="Experiments",
                        )

                def create_experiment() -> None:
                    name = new_name_input.value.strip()
                    if not name:
                        create_result.set_text("Name required.")
                        create_result.style(f"color: {COLORS['warning']}")
                        return
                    try:
                        engine.tracker.create_experiment(name)
                        new_name_input.set_value("")
                        create_result.set_text(f"Created '{name}'.")
                        create_result.style(f"color: {COLORS['success']}")
                        refresh_experiments()
                    except Exception as exc:
                        create_result.set_text(f"Error: {exc}")
                        create_result.style(f"color: {COLORS['error']}")

                ui.button(
                    "Create",
                    icon="add",
                    on_click=create_experiment,
                ).props("color=indigo")

                refresh_experiments()
