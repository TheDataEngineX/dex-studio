"""ML Models page — model registry browser and prediction playground.

Route: ``/models``

Drives DEX engine endpoints (requires ML router mounted):
    GET  /api/v1/models         → list all registered models
    GET  /api/v1/models/{name}  → model metadata
    POST /api/v1/predict        → run inference
"""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import metric_card
from dex_studio.components.page_layout import page_layout
from dex_studio.theme import COLORS

_MODEL_COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "version", "label": "Version", "field": "version", "align": "left"},
    {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
    {
        "name": "created_at",
        "label": "Created",
        "field": "created_at",
        "align": "left",
    },
]


def _render_503_warning() -> None:
    """Show a warning card when the ML router is not mounted."""
    with ui.card().classes("dex-card w-full").style(f"border-color: {COLORS['warning']}"):
        ui.label("ML Router Not Configured").classes("font-semibold text-sm").style(
            f"color: {COLORS['warning']}"
        )
        ui.label(
            "The DEX engine ML router is not mounted or the model "
            "server is not configured. Start the engine with ML "
            "endpoints enabled."
        ).classes("text-xs mt-1").style(f"color: {COLORS['text_muted']}")


def _render_model_meta(meta: dict[str, Any], name: str) -> None:
    """Render model metadata inside a card."""
    with ui.card().classes("dex-card w-full"):
        ui.label(meta.get("name", name)).classes("font-bold text-lg").style(
            f"color: {COLORS['text_primary']}"
        )
        if meta.get("description"):
            ui.label(meta["description"]).classes("text-sm mt-1").style(
                f"color: {COLORS['text_secondary']}"
            )
        with ui.grid(columns=2).classes("gap-x-6 gap-y-2 mt-3"):
            for key in ("version", "stage", "created_at"):
                ui.label(key).classes("text-xs font-mono").style(f"color: {COLORS['text_muted']}")
                ui.label(str(meta.get(key, "—"))).classes("text-sm").style(
                    f"color: {COLORS['text_primary']}"
                )

        _render_model_metrics(meta.get("metrics", {}))
        _render_model_params(meta.get("parameters", {}))


def _render_model_metrics(metrics: dict[str, Any]) -> None:
    """Render model metrics section."""
    if not metrics:
        return
    ui.label("Metrics").classes("section-title mt-3")
    with ui.row().classes("gap-3 flex-wrap"):
        for mk, mv in metrics.items():
            formatted = f"{mv:.4f}" if isinstance(mv, float) else str(mv)
            metric_card(mk, formatted)


def _render_model_params(params: dict[str, Any]) -> None:
    """Render model parameters section."""
    if not params:
        return
    ui.label("Parameters").classes("section-title mt-3")
    with ui.grid(columns=2).classes("gap-x-4 gap-y-1"):
        for pk, pv in params.items():
            ui.label(pk).classes("text-xs font-mono").style(f"color: {COLORS['text_muted']}")
            ui.label(str(pv)).classes("text-xs").style(f"color: {COLORS['text_primary']}")


def _render_prediction_playground(client: DexClient) -> None:
    """Render the prediction playground section."""
    ui.label("Prediction Playground").classes("section-title mt-6")
    ui.label("Send a prediction request to a registered model.").classes("text-xs").style(
        f"color: {COLORS['text_muted']}"
    )

    pred_model = (
        ui.input(label="Model Name", placeholder="e.g. weather_regressor")
        .classes("w-64")
        .props("outlined dark")
    )
    pred_features = (
        ui.textarea(
            label="Features (JSON array)",
            placeholder='[{"temp": 20, "humidity": 65}]',
        )
        .classes("w-full")
        .props("outlined dark")
    )

    pred_result = ui.column().classes("w-full mt-2")

    async def run_prediction() -> None:
        name = pred_model.value
        raw = pred_features.value
        if not name or not raw:
            return
        pred_result.clear()
        with pred_result:
            try:
                parsed = json.loads(raw)
                # API takes a single features dict; accept a list and use first element
                features: dict[str, Any] = parsed[0] if isinstance(parsed, list) else parsed
                if not isinstance(features, dict):
                    ui.label("Features must be a JSON object or array of objects.").style(
                        f"color: {COLORS['error']}"
                    )
                    return
            except json.JSONDecodeError as exc:
                ui.label(f"Invalid JSON: {exc}").style(f"color: {COLORS['error']}")
                return

            try:
                result = await client.predict(name, features)
            except DexAPIError as exc:
                ui.label(f"Prediction failed: {exc}").style(f"color: {COLORS['error']}")
                return

            with ui.card().classes("dex-card w-full"):
                ui.label("Prediction Result").classes("font-semibold text-sm").style(
                    f"color: {COLORS['text_primary']}"
                )
                ui.code(json.dumps(result, indent=2, default=str)).classes("w-full mt-2")

    ui.button("Predict", icon="play_arrow", on_click=run_prediction).props("color=indigo").classes(
        "mt-2"
    )


@ui.page("/models")
async def ml_models_page() -> None:
    """Render the ML model registry browser."""
    with page_layout("ML Models", active_route="/models") as _content:
        client: DexClient | None = app.storage.general.get("client")
        if client is None:
            ui.label("No connection configured.").style(f"color: {COLORS['error']}")
            return

        # -- Model list --
        ui.label("Model Registry").classes("section-title")
        try:
            models_resp = await client.list_models()
            models: list[dict[str, Any]] = models_resp.get("models", [])
            total = models_resp.get("total", 0)
        except DexAPIError as exc:
            if exc.status_code == 503:
                _render_503_warning()
            else:
                ui.label(f"Error: {exc}").style(f"color: {COLORS['error']}")
            models = []
            total = 0

        metric_card("Registered Models", total)

        if models:
            rows = [
                {
                    "name": m.get("name", "—"),
                    "version": m.get("version", "—"),
                    "stage": m.get("stage", "—"),
                    "created_at": m.get("created_at", "—"),
                }
                for m in models
            ]
            ui.table(columns=_MODEL_COLUMNS, rows=rows).classes("w-full mt-4")

            # -- Model detail --
            ui.label("Model Detail").classes("section-title mt-6")
            model_select = (
                ui.select(
                    label="Select model",
                    options=[m["name"] for m in models],
                )
                .classes("w-64")
                .props("outlined dark")
            )

            detail_container = ui.column().classes("w-full gap-2 mt-2")

            async def show_model_detail() -> None:
                name = model_select.value
                if not name:
                    return
                detail_container.clear()
                with detail_container:
                    try:
                        meta = await client.get_model(name)
                    except DexAPIError as exc:
                        ui.label(f"Error: {exc}").style(f"color: {COLORS['error']}")
                        return
                    _render_model_meta(meta, name)

            model_select.on_value_change(show_model_detail)

        _render_prediction_playground(client)
