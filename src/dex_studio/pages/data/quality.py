from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import QualityState


def data_quality() -> rx.Component:
    return page_shell(
        "Data Quality",
        rx.cond(
            QualityState.error != "",
            rx.callout.root(rx.callout.text(QualityState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(QualityState.is_loading, rx.spinner(), rx.fragment()),
        rx.card(
            rx.text("Overall Quality Score", size="1", color="gray"),
            rx.heading(QualityState.quality_score, size="6"),
            margin_bottom="6",
            width="fit-content",
        ),
        rx.heading("Checks", size="3", margin_bottom="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Check"),
                    rx.table.column_header_cell("Table"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Score"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    QualityState.quality_checks,
                    lambda c: rx.table.row(
                        rx.table.cell(c["name"]),
                        rx.table.cell(c["table"]),
                        rx.table.cell(
                            rx.badge(
                                c["status"],
                                color_scheme=rx.cond(c["status"] == "passed", "green", "red"),
                            )
                        ),
                        rx.table.cell(c["score"]),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=QualityState.load_quality,
    )
