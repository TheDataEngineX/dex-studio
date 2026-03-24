"""ML predictions page — inference playground.

Route: ``/ml/predictions``
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_INPUT_PROPS = "outlined dark"


def _parse_features(raw: str) -> dict[str, Any] | str:
    """Parse a JSON string into a features dict.

    Returns the dict on success, or an error message string on failure.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"

    if isinstance(parsed, list):
        if not parsed or not isinstance(parsed[0], dict):
            return "Features must be a JSON object or array of objects."
        return parsed[0]

    if isinstance(parsed, dict):
        return parsed

    return "Features must be a JSON object."


def _render_prediction_result(prediction: Any) -> None:
    """Render a prediction result card."""
    with ui.card().classes("dex-card w-full"):
        ui.label("Prediction Result").classes("font-semibold text-sm").style(
            f"color: {COLORS['text_primary']}"
        )
        display = (
            json.dumps(prediction, indent=2, default=str)
            if isinstance(prediction, dict)
            else str(prediction)
        )
        ui.code(display).classes("w-full mt-2")


@ui.page("/ml/predictions")
async def ml_predictions_page() -> None:
    """Render the ML predictions playground."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/predictions")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Predictions")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                if engine.serving_engine is None:
                    ui.label("Serving engine unavailable.").style(f"color: {COLORS['warning']}")
                    return

                ui.label("Prediction Playground").classes("section-title")
                ui.label("Send a prediction request to a registered model.").classes(
                    "text-xs"
                ).style(f"color: {COLORS['text_muted']}")

                # Fetch model names for select
                model_names: list[str] = engine.model_registry.list_models()

                with ui.column().classes("gap-3 w-full max-w-xl mt-2"):
                    model_input: ui.select | ui.input
                    if model_names:
                        model_input = (
                            ui.select(
                                label="Model",
                                options=model_names,
                                value=model_names[0],
                            )
                            .classes("w-64")
                            .props(_INPUT_PROPS)
                        )
                    else:
                        model_input = (
                            ui.input(
                                label="Model Name",
                                placeholder="e.g. weather_regressor",
                            )
                            .classes("w-64")
                            .props(_INPUT_PROPS)
                        )

                    features_input = (
                        ui.textarea(
                            label="Features (JSON object)",
                            placeholder='{"temp": 20, "humidity": 65}',
                        )
                        .classes("w-full")
                        .props(_INPUT_PROPS)
                    )

                    result_container = ui.column().classes("w-full mt-2")

                    async def run_prediction() -> None:
                        name: str = model_input.value or ""
                        raw = features_input.value
                        if not name or not raw:
                            return
                        result_container.clear()
                        with result_container:
                            parsed = _parse_features(raw)
                            if isinstance(parsed, str):
                                ui.label(parsed).style(f"color: {COLORS['error']}")
                                return
                            try:
                                prediction = await asyncio.to_thread(
                                    engine.serving_engine.predict,
                                    name,
                                    parsed,
                                )
                            except Exception as exc:
                                ui.label(f"Prediction failed: {exc}").style(
                                    f"color: {COLORS['error']}"
                                )
                                return
                            _render_prediction_result(prediction)

                    ui.button(
                        "Predict",
                        icon="play_arrow",
                        on_click=run_prediction,
                    ).props("color=indigo")
