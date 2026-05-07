from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _trace_row(trace: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(trace["id"]),
        rx.table.cell(trace["name"]),
        rx.table.cell(trace["duration_ms"]),
        rx.table.cell(
            rx.badge(
                trace["status"],
                color_scheme=rx.cond(trace["status"] == "ok", "green", "red"),
            )
        ),
    )


def ai_traces() -> rx.Component:
    return page_shell(
        "AI Traces",
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("ID"),
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Duration (ms)"),
                    rx.table.column_header_cell("Status"),
                )
            ),
            rx.table.body(rx.foreach(AIState.traces, _trace_row)),
        ),
        on_mount=AIState.load_traces,
    )
