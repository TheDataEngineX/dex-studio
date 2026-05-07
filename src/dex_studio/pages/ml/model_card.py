from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def _model_option(m: dict) -> rx.Component:
    return rx.select.item(m["name"], value=m["name"])


def _meta_row(label: str, value: str) -> rx.Component:
    return rx.hstack(
        rx.text(label, weight="bold", size="2", width="140px"),
        rx.text(value, size="2"),
        width="100%",
    )


def ml_model_card() -> rx.Component:
    return page_shell(
        "Model Card",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.select.root(
            rx.select.trigger(placeholder="Select model"),
            rx.select.content(
                rx.foreach(MLState.models, _model_option),
            ),
            on_change=MLState.select_experiment,
            margin_bottom="4",
        ),
        rx.cond(
            MLState.selected_experiment != "",
            rx.card(
                rx.vstack(
                    rx.heading(MLState.selected_experiment, size="4"),
                    rx.foreach(
                        MLState.models,
                        lambda m: rx.cond(
                            m["name"] == MLState.selected_experiment,
                            rx.vstack(
                                _meta_row("Version", m["version"]),
                                _meta_row("Stage", m["stage"]),
                                _meta_row("Framework", m["framework"]),
                                _meta_row("Created", m["created_at"]),
                                spacing="2",
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                    ),
                    spacing="3",
                    align="start",
                    width="100%",
                )
            ),
            rx.text("Select a model to view its card.", size="2", color="gray"),
        ),
        on_mount=MLState.load_models,
    )
