"""ML models page — model registry browser with promote action.

Route: ``/ml/models``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.status_badge import status_badge
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_MODEL_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "version", "label": "Version", "field": "version", "align": "left"},
    {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
    {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
]

_STAGES = ["development", "staging", "production", "archived"]


@ui.page("/ml/models")
async def ml_models_page() -> None:
    """Render the ML models registry page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/models")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Models")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                models: list[dict[str, Any]] = []

                try:
                    resp = await client.list_models()
                    models = resp.get("models", [])
                except DexAPIError as exc:
                    ui.label(f"Error fetching models: {exc}").style(f"color: {COLORS['error']}")

                ui.label("Model Registry").classes("section-title")

                if not models:
                    empty_state("No models registered", icon="model_training")
                else:
                    rows = [
                        {
                            "name": m.get("name", "—"),
                            "version": m.get("version", "—"),
                            "stage": m.get("stage", "—"),
                            "created_at": m.get("created_at", "—"),
                        }
                        for m in models
                    ]
                    data_table(_MODEL_COLUMNS, rows, title="Models")

                    # -- Promote action --
                    ui.label("Promote Model").classes("section-title mt-6")
                    ui.label("Move a model to a new lifecycle stage.").classes("text-xs").style(
                        f"color: {COLORS['text_muted']}"
                    )

                    model_names = [m.get("name", "") for m in models if m.get("name")]
                    promote_model_select = (
                        ui.select(label="Model", options=model_names)
                        .classes("w-64")
                        .props("outlined dark")
                    )
                    promote_stage_select = (
                        ui.select(label="Target Stage", options=_STAGES)
                        .classes("w-48")
                        .props("outlined dark")
                    )
                    promote_result_label = (
                        ui.label("").classes("text-xs").style(f"color: {COLORS['text_muted']}")
                    )
                    promote_badge_container = ui.row().classes("items-center gap-2 mt-1")

                    async def promote_model() -> None:
                        model_name = promote_model_select.value
                        stage = promote_stage_select.value
                        if not model_name or not stage:
                            promote_result_label.set_text("Select a model and stage.")
                            promote_result_label.style(f"color: {COLORS['warning']}")
                            return
                        try:
                            result = await client.promote_model(model_name, stage)
                            new_stage: str = result.get("stage", stage)
                            promote_result_label.set_text(f"Promoted '{model_name}' to:")
                            promote_result_label.style(f"color: {COLORS['success']}")
                            promote_badge_container.clear()
                            with promote_badge_container:
                                status_badge(new_stage)
                        except DexAPIError as exc:
                            promote_result_label.set_text(f"Error: {exc}")
                            promote_result_label.style(f"color: {COLORS['error']}")

                    ui.button(
                        "Promote",
                        icon="upgrade",
                        on_click=promote_model,
                    ).props("color=indigo").classes("mt-2")
