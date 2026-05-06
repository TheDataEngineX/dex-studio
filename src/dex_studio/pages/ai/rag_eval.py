from __future__ import annotations

from collections.abc import AsyncGenerator

import reflex as rx

from dex_studio.components.layout import page_shell


class RagEvalState(rx.State):
    metrics: list[dict] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def load_eval(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        self.metrics = []
        self.is_loading = False


def _metric_row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["query"]),
        rx.table.cell(row["precision"]),
        rx.table.cell(row["recall"]),
        rx.table.cell(row["faithfulness"]),
    )


def ai_rag_eval() -> rx.Component:
    return page_shell(
        "RAG Evaluation",
        rx.cond(RagEvalState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            RagEvalState.error != "",
            rx.callout.root(
                rx.callout.text(RagEvalState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.cond(
            RagEvalState.metrics.length() == 0,
            rx.callout.root(
                rx.callout.text(
                    "No evaluation data. Run RAG eval from the CLI or configure eval datasets."
                ),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Query"),
                        rx.table.column_header_cell("Precision"),
                        rx.table.column_header_cell("Recall"),
                        rx.table.column_header_cell("Faithfulness"),
                    )
                ),
                rx.table.body(rx.foreach(RagEvalState.metrics, _metric_row)),
            ),
        ),
        on_mount=RagEvalState.load_eval,
    )
