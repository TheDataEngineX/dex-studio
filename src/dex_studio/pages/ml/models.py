"""ML models page — model registry browser.

Route: ``/ml/models``
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

_MODEL_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {
        "name": "versions",
        "label": "Versions",
        "field": "versions",
        "align": "left",
    },
]


@ui.page("/ml/models")
async def ml_models_page() -> None:
    """Render the ML models registry page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/models")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Models")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                model_names: list[str] = engine.model_registry.list_models()

                ui.label("Model Registry").classes("section-title")

                if not model_names:
                    empty_state("No models registered", icon="model_training")
                    return

                rows: list[dict[str, Any]] = []
                for name in model_names:
                    versions = engine.model_registry.list_versions(name)
                    rows.append(
                        {
                            "name": name,
                            "versions": ", ".join(versions) if versions else "\u2014",
                        }
                    )

                data_table(_MODEL_COLUMNS, rows, title="Models")
