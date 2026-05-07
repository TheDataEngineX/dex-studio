from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _collection_card(col: dict) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.text(col["name"], size="3", weight="bold"),
                rx.text(
                    rx.el.span(col["doc_count"]),
                    rx.el.span(" documents"),
                    size="2",
                    color_scheme="gray",
                ),
                spacing="1",
                align_items="flex-start",
            ),
            rx.cond(
                col.contains("type"), rx.badge(col["type"], color_scheme="indigo"), rx.fragment()
            ),
            justify="between",
        ),
        padding="4",
    )


def ai_collections() -> rx.Component:
    return page_shell(
        "Knowledge Collections",
        rx.heading("Document Collections", size="5", margin_bottom="4"),
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(
            AIState.memory_collections.length() == 0,
            rx.callout.root(
                rx.callout.text(
                    "No collections configured. Add collections via dex.yaml or the DEX CLI."
                ),
                color_scheme="gray",
            ),
            rx.vstack(
                rx.foreach(AIState.memory_collections, _collection_card),
                spacing="3",
            ),
        ),
        on_mount=AIState.load_memory,
    )
