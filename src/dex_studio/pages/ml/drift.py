from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def ml_drift() -> rx.Component:
    return page_shell(
        "Drift Monitor",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.card(
            rx.text("Overall Drift Score", size="1", color="gray"),
            rx.heading(MLState.drift_score, size="6"),
            margin_bottom="6",
            width="fit-content",
        ),
        rx.heading("Feature Drift", size="3", margin_bottom="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Feature"),
                    rx.table.column_header_cell("PSI"),
                    rx.table.column_header_cell("Status"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    MLState.drift_features,
                    lambda f: rx.table.row(
                        rx.table.cell(f["name"]),
                        rx.table.cell(f["psi"]),
                        rx.table.cell(
                            rx.badge(
                                f["status"],
                                color_scheme=rx.cond(f["status"] == "ok", "green", "red"),
                            )
                        ),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=MLState.load_drift,
    )
