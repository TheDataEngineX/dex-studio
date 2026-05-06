from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def _feature_group_card(fg: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("layers", size=16),
                rx.text(fg["name"], weight="bold", size="2"),
                spacing="2",
            ),
            rx.text(fg["description"], size="1", color="gray"),
            rx.hstack(
                rx.badge(fg["entity"], variant="outline"),
                rx.text(fg["feature_count"], " features", size="1", color="gray"),
                spacing="2",
            ),
            spacing="2",
            align="start",
        ),
        width="100%",
    )


def ml_features() -> rx.Component:
    return page_shell(
        "Feature Store",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.grid(
            rx.foreach(MLState.feature_groups, _feature_group_card),
            columns="2",
            gap="4",
        ),
        on_mount=MLState.load_features,
    )
