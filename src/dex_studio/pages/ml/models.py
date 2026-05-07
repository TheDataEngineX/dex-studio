from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def ml_models() -> rx.Component:
    return page_shell(
        "Model Registry",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Version"),
                    rx.table.column_header_cell("Stage"),
                    rx.table.column_header_cell("Framework"),
                    rx.table.column_header_cell("Action"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    MLState.models,
                    lambda m: rx.table.row(
                        rx.table.cell(m["name"]),
                        rx.table.cell(m["version"]),
                        rx.table.cell(
                            rx.badge(
                                m["stage"],
                                color_scheme=rx.cond(
                                    m["stage"] == "production",
                                    "green",
                                    rx.cond(m["stage"] == "staging", "yellow", "gray"),
                                ),
                            )
                        ),
                        rx.table.cell(m["framework"]),
                        rx.table.cell(
                            rx.button(
                                "Promote",
                                size="1",
                                on_click=MLState.promote_model(m["name"], "production"),
                            )
                        ),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=MLState.load_models,
    )
