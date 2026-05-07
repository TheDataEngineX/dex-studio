from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _vector_row(col: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(col["name"], weight="bold")),
        rx.table.cell(col["dimension"]),
        rx.table.cell(col["doc_count"]),
    )


def ai_vectors() -> rx.Component:
    return page_shell(
        "Vector Store",
        rx.heading("Vector Collections", size="5", margin_bottom="4"),
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(
            AIState.memory_collections.length() == 0,
            rx.callout.root(
                rx.callout.text("No vector collections found. Configure collections in dex.yaml."),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Dimension"),
                        rx.table.column_header_cell("Documents"),
                    )
                ),
                rx.table.body(rx.foreach(AIState.memory_collections, _vector_row)),
            ),
        ),
        on_mount=AIState.load_memory,
    )
