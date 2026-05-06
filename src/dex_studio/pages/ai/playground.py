from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ai import AIState


def _agent_name(agent: dict) -> str:
    return agent["name"]


def _chat_bubble(msg: dict) -> rx.Component:
    return page_shell(
        "Playground",
        rx.text(msg["content"], size="2"),
        background=rx.cond(msg["role"] == "user", "var(--indigo-3)", "var(--gray-3)"),
        padding="2",
        border_radius="md",
        margin_bottom="2",
        max_width="80%",
        align_self=rx.cond(msg["role"] == "user", "flex-end", "flex-start"),
    )


def ai_playground() -> rx.Component:
    return page_shell(
        "Playground",
        rx.heading("AI Playground", size="5", margin_bottom="4"),
        rx.cond(AIState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            AIState.error != "",
            rx.callout.root(rx.callout.text(AIState.error), color_scheme="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.hstack(
            # Left: agent selector
            rx.card(
                rx.vstack(
                    rx.text("Select Agent", size="2", weight="bold"),
                    rx.select(
                        AIState.agents.foreach(_agent_name),
                        value=AIState.selected_agent,
                        on_change=AIState.select_agent,
                        placeholder="Choose an agent...",
                    ),
                    spacing="3",
                ),
                padding="4",
                min_width="220px",
                max_width="240px",
            ),
            # Right: chat
            rx.card(
                rx.vstack(
                    rx.box(
                        rx.vstack(
                            rx.foreach(AIState.chat_messages, _chat_bubble),
                            spacing="0",
                            align_items="stretch",
                        ),
                        overflow_y="auto",
                        height="400px",
                        padding="2",
                        border="1px solid var(--gray-4)",
                        border_radius="md",
                        margin_bottom="3",
                    ),
                    rx.hstack(
                        rx.input(
                            placeholder="Type a message...",
                            value=AIState.chat_input,
                            on_change=AIState.set_chat_input,
                            on_key_down=rx.cond(
                                rx.Var.create("event.key === 'Enter'"),
                                AIState.send_message,
                                rx.noop(),
                            ),
                            flex="1",
                        ),
                        rx.button(
                            "Send",
                            on_click=AIState.send_message,
                            color_scheme="indigo",
                            disabled=rx.cond(
                                AIState.selected_agent == "",
                                True,
                                False,
                            ),
                        ),
                        spacing="2",
                    ),
                    spacing="0",
                ),
                padding="4",
                flex="1",
            ),
            spacing="4",
            align_items="flex-start",
        ),
        on_mount=AIState.load_agents,
    )
