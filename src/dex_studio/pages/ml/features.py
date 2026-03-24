"""ML features page — feature store browser.

Route: ``/ml/features``
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

_GROUP_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Group", "field": "name", "align": "left"},
]


@ui.page("/ml/features")
async def ml_features_page() -> None:
    """Render the ML feature store page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/features")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Feature Store")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                if engine.feature_store is None:
                    ui.label("Feature store unavailable.").style(f"color: {COLORS['warning']}")
                    return

                group_names: list[str] = engine.feature_store.list_feature_groups()

                ui.label("Feature Groups").classes("section-title")

                if not group_names:
                    empty_state("No feature groups found", icon="dataset")
                    return

                rows: list[dict[str, Any]] = [{"name": name} for name in group_names]
                data_table(
                    _GROUP_COLUMNS,
                    rows,
                    title="Feature Groups",
                )
