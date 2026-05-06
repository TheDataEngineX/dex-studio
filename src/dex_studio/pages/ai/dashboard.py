from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import metric_card, page_shell
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


def ai_dashboard() -> rx.Component:
    return page_shell(
        "AI Overview",
        rx.heading("AI Dashboard", size="5", margin_bottom="4"),
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.grid(
            metric_card("bot", "Agents", AIState.agents.length(), accent="cyan"),
            metric_card("wrench", "Tools", AIState.tools.length(), accent="cyan"),
            metric_card("waypoints", "Traces", AIState.traces.length(), accent="cyan"),
            columns="3",
            gap="4",
            margin_bottom="6",
        ),
        rx.heading("Recent Traces", size="4", margin_bottom="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("ID"),
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Duration (ms)"),
                    rx.table.column_header_cell("Status"),
                )
            ),
            rx.table.body(
                rx.foreach(AIState.traces[:5], _trace_row),
            ),
        ),
        on_mount=[AIState.load_agents, AIState.load_traces],
    )
