from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _tool_row(tool: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(tool["name"], weight="bold")),
        rx.table.cell(tool["description"]),
    )


def ai_tools() -> rx.Component:
    return page_shell(
        "Agent Tools",
        rx.heading("Tools", size="5", margin_bottom="4"),
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
                    rx.table.column_header_cell("Description"),
                )
            ),
            rx.table.body(rx.foreach(AIState.tools, _tool_row)),
        ),
        on_mount=AIState.load_tools,
    )
