from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _workflow_row(wf: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(wf["name"], weight="bold")),
        rx.table.cell(wf["steps"]),
        rx.table.cell(
            rx.badge(
                wf["status"],
                color_scheme=rx.cond(wf["status"] == "active", "green", "gray"),
            )
        ),
    )


def ai_workflows() -> rx.Component:
    return page_shell(
        "Workflows",
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(
            AIState.workflows.length() == 0,
            rx.callout.root(
                rx.callout.text("No workflows configured. Define workflows in dex.yaml."),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Steps"),
                        rx.table.column_header_cell("Status"),
                    )
                ),
                rx.table.body(rx.foreach(AIState.workflows, _workflow_row)),
            ),
        ),
        on_mount=AIState.load_workflows,
    )
