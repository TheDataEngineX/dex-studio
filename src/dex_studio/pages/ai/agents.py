from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _agent_row(agent: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.link(
                agent["name"],
                on_click=AIState.select_agent(agent["name"]),
                cursor="pointer",
                color_scheme="indigo",
            )
        ),
        rx.table.cell(agent["type"]),
        rx.table.cell(
            rx.badge(
                agent["status"],
                color_scheme=rx.cond(agent["status"] == "available", "green", "gray"),
            )
        ),
    )


def _agent_detail() -> rx.Component:
    return rx.cond(
        AIState.selected_agent != "",
        rx.card(
            rx.heading(AIState.selected_agent, size="4", margin_bottom="2"),
            rx.text("Selected agent — use the Playground to chat.", size="2", color_scheme="gray"),
            rx.link("Open Playground", href="/ai/playground", color_scheme="indigo"),
            padding="4",
            margin_top="4",
        ),
        rx.fragment(),
    )


def ai_agents() -> rx.Component:
    return page_shell(
        "Agents",
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
                    rx.table.column_header_cell("Type"),
                    rx.table.column_header_cell("Status"),
                )
            ),
            rx.table.body(rx.foreach(AIState.agents, _agent_row)),
        ),
        _agent_detail(),
        on_mount=AIState.load_agents,
    )
