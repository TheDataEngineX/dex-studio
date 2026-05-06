from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.system import SystemState


def _component_row(comp: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(comp["name"], weight="bold")),
        rx.table.cell(
            rx.badge(
                comp["status"],
                color_scheme=rx.cond(comp["status"] == "ok", "green", "red"),
            )
        ),
        rx.table.cell(comp.get("latency_ms", "—")),
    )


def system_components() -> rx.Component:
    return page_shell(
        "System Components",
        rx.heading("Components", size="5", margin_bottom="4"),
        rx.cond(SystemState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            SystemState.error != "",
            rx.callout.root(
                rx.callout.text(SystemState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Latency (ms)"),
                )
            ),
            rx.table.body(rx.foreach(SystemState.components_list, _component_row)),
        ),
        on_mount=SystemState.load_components,
    )
