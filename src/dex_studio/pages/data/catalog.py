from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import SourceState


def _source_card(s: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("database", size=16),
                rx.text(s["name"], weight="bold", size="2"),
                spacing="2",
            ),
            rx.badge(s["type"], variant="outline"),
            rx.badge(
                s["status"],
                color_scheme=rx.cond(s["status"] == "active", "green", "gray"),
            ),
            spacing="2",
            align="start",
        ),
        width="100%",
    )


def data_catalog() -> rx.Component:
    return page_shell(
        "Data Catalog",
        rx.cond(
            SourceState.error != "",
            rx.callout.root(rx.callout.text(SourceState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(SourceState.is_loading, rx.spinner(), rx.fragment()),
        rx.grid(
            rx.foreach(SourceState.sources, _source_card),
            columns="3",
            gap="4",
        ),
        on_mount=SourceState.load_sources,
    )
