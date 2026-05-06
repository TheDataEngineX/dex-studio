from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import LineageState


def data_lineage() -> rx.Component:
    return page_shell(
        "Data Lineage",
        rx.cond(
            LineageState.error != "",
            rx.callout.root(rx.callout.text(LineageState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(LineageState.is_loading, rx.spinner(), rx.fragment()),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("ID"),
                    rx.table.column_header_cell("Source"),
                    rx.table.column_header_cell("Target"),
                    rx.table.column_header_cell("Timestamp"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    LineageState.lineage_events,
                    lambda e: rx.table.row(
                        rx.table.cell(e["id"]),
                        rx.table.cell(e["source"]),
                        rx.table.cell(e["target"]),
                        rx.table.cell(e["timestamp"]),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=LineageState.load_lineage,
    )
