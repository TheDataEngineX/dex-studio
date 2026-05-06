from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _collection_row(col: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(col["name"], weight="bold")),
        rx.table.cell(col["doc_count"]),
    )


def ai_memory() -> rx.Component:
    return page_shell(
        "Agent Memory",
        rx.heading("Memory Collections", size="5", margin_bottom="4"),
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Documents"),
                )
            ),
            rx.table.body(rx.foreach(AIState.memory_collections, _collection_row)),
        ),
        on_mount=AIState.load_memory,
    )
