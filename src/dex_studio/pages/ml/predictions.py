from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def _model_option(m: dict) -> rx.Component:
    return rx.select.item(m["name"], value=m["name"])


def ml_predictions() -> rx.Component:
    return page_shell(
        "Predictions",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.vstack(
            rx.select.root(
                rx.select.trigger(placeholder="Select model"),
                rx.select.content(
                    rx.foreach(MLState.models, _model_option),
                ),
                on_change=MLState.run_prediction,
            ),
            rx.text_area(
                value=MLState.predict_input,
                on_change=MLState.set_predict_input,
                placeholder='{"feature1": 0.5, "feature2": 1.2}',
                rows="6",
                font_family="monospace",
                width="100%",
            ),
            rx.button(
                "Predict",
                loading=MLState.is_loading,
            ),
            rx.cond(
                MLState.predict_output != "",
                rx.code_block(
                    MLState.predict_output,
                    language="json",
                    width="100%",
                ),
                rx.fragment(),
            ),
            width="100%",
            spacing="3",
        ),
        on_mount=MLState.load_models,
    )
