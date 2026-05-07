"""AI Copilot sidebar — persistent right-panel backed by dex agent chat/stream."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any, cast

import reflex as rx

_COPILOT_AGENT = os.getenv("DEX_COPILOT_AGENT", "assistant")


class CopilotState(rx.State):
    messages: list[dict[str, Any]] = []
    input_text: str = ""
    is_open: bool = False
    is_streaming: bool = False
    error: str = ""

    @rx.event
    def toggle(self) -> None:
        self.is_open = not self.is_open

    @rx.event
    def open(self) -> None:
        self.is_open = True

    @rx.event
    def close(self) -> None:
        self.is_open = False

    @rx.event
    def set_input(self, value: str) -> None:
        self.input_text = value

    @rx.event
    def clear(self) -> None:
        self.messages = []
        self.error = ""

    @rx.event
    async def send(self) -> AsyncGenerator[None]:
        if not self.input_text.strip():
            return
        user_msg = self.input_text.strip()
        self.messages = [*self.messages, {"role": "user", "content": user_msg}]
        self.messages = [*self.messages, {"role": "assistant", "content": "", "is_streaming": True}]
        self.input_text = ""
        self.is_streaming = True
        self.error = ""
        yield

        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None:
                self._replace_last("Engine not initialized — set DEX_CONFIG_PATH", streaming=False)
                self.error = "Engine not initialized"
                return
            agent = eng.agents.get(_COPILOT_AGENT)
            if agent is None:
                self._replace_last(
                    f"Agent '{_COPILOT_AGENT}' not found — set DEX_COPILOT_AGENT", streaming=False
                )
                self.error = f"Agent '{_COPILOT_AGENT}' not configured"
                return
            import asyncio

            result = await asyncio.wait_for(agent.run(user_msg), timeout=60)
            reply = result.get("reply") or result.get("content") or str(result)
            self._replace_last(reply, streaming=False)
        except TimeoutError:
            self._replace_last("Agent timed out", streaming=False)
            self.error = "Agent timed out"
        except Exception as exc:
            self._replace_last(f"Error: {exc}", streaming=False)
            self.error = str(exc)
        finally:
            self.is_streaming = False
            yield

    def _replace_last(self, content: str, *, streaming: bool) -> None:
        """Replace the last (assistant placeholder) message in place."""
        if not self.messages:
            return
        last = dict(self.messages[-1])
        last["content"] = content
        last["is_streaming"] = streaming
        self.messages = [*self.messages[:-1], last]


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------


def _message_bubble(msg: dict[str, Any]) -> rx.Component:
    is_user = msg.get("role") == "user"
    return cast(
        rx.Component,
        rx.box(
            rx.hstack(
                rx.cond(
                    ~is_user,
                    rx.icon("bot", size=14, color="var(--accent-9)", flex_shrink="0"),
                    rx.fragment(),
                ),
                rx.box(
                    rx.text(msg.get("content", ""), size="2", white_space="pre-wrap"),
                    rx.cond(
                        msg.get("is_streaming", False),
                        rx.text(
                            "▍",
                            size="2",
                            color="var(--accent-9)",
                            animation="blink 1s step-end infinite",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="2",
                align="start",
            ),
            background=rx.cond(is_user, "var(--accent-3)", "var(--gray-2)"),
            border_radius="var(--radius-3)",
            padding="2 3",
            margin_bottom="2",
            align_self=rx.cond(is_user, "flex-end", "flex-start"),
            max_width="90%",
        ),
    )


def copilot_panel() -> rx.Component:
    """The slide-in copilot drawer — shown when CopilotState.is_open."""
    return cast(
        rx.Component,
        rx.cond(
            CopilotState.is_open,
            rx.box(
                # Header
                rx.hstack(
                    rx.hstack(
                        rx.icon("bot", size=16, color="var(--accent-9)"),
                        rx.heading("AI Copilot", size="3"),
                        spacing="2",
                    ),
                    rx.spacer(),
                    rx.hstack(
                        rx.icon_button(
                            rx.icon("trash-2", size=14),
                            size="1",
                            variant="ghost",
                            aria_label="Clear conversation",
                            on_click=CopilotState.clear,
                        ),
                        rx.icon_button(
                            rx.icon("x", size=14),
                            size="1",
                            variant="ghost",
                            aria_label="Close copilot",
                            on_click=CopilotState.close,
                        ),
                        spacing="1",
                    ),
                    align="center",
                    padding="3",
                    border_bottom="1px solid var(--gray-4)",
                ),
                # Messages
                rx.box(
                    rx.cond(
                        CopilotState.messages == [],
                        rx.vstack(
                            rx.icon("sparkles", size=32, color="var(--gray-6)"),
                            rx.text(
                                "Ask me anything about your data, pipelines, or models.",
                                size="2",
                                color="gray",
                                text_align="center",
                            ),
                            align="center",
                            justify="center",
                            height="100%",
                            padding="6",
                        ),
                        rx.vstack(
                            rx.foreach(CopilotState.messages, _message_bubble),
                            align="stretch",
                            padding="3",
                            padding_bottom="2",
                        ),
                    ),
                    flex="1",
                    overflow_y="auto",
                ),
                # Error
                rx.cond(
                    CopilotState.error != "",
                    rx.callout.root(
                        rx.callout.text(CopilotState.error, size="1"),
                        color_scheme="red",
                        margin="2",
                    ),
                    rx.fragment(),
                ),
                # Input
                rx.hstack(
                    rx.text_area(
                        placeholder="Ask about your data...",
                        value=CopilotState.input_text,
                        on_change=CopilotState.set_input,
                        rows="2",
                        resize="none",
                        flex="1",
                        font_size="0.85rem",
                        on_key_down=rx.cond(
                            rx.Var.create("event.key === 'Enter' && !event.shiftKey"),
                            CopilotState.send,
                            rx.noop(),
                        ),
                    ),
                    rx.icon_button(
                        rx.cond(
                            CopilotState.is_streaming,
                            rx.spinner(size="1"),
                            rx.icon("send", size=14),
                        ),
                        on_click=CopilotState.send,
                        disabled=CopilotState.is_streaming,
                        color_scheme="indigo",
                        size="2",
                        align_self="flex-end",
                        aria_label="Send message",
                    ),
                    spacing="2",
                    padding="3",
                    border_top="1px solid var(--gray-4)",
                    align="end",
                ),
                # Panel container
                position="fixed",
                right="0",
                top="0",
                height="100vh",
                width="360px",
                background="var(--gray-1)",
                border_left="1px solid var(--gray-4)",
                z_index="200",
                display="flex",
                flex_direction="column",
                box_shadow="var(--shadow-5)",
            ),
            rx.fragment(),
        ),
    )


def copilot_toggle_button() -> rx.Component:
    """Floating toggle button — place in page_shell or header."""
    return cast(
        rx.Component,
        rx.icon_button(
            rx.icon("bot", size=16),
            on_click=CopilotState.toggle,
            position="fixed",
            bottom="6",
            right=rx.cond(CopilotState.is_open, "368px", "4"),
            z_index="150",
            color_scheme="indigo",
            size="3",
            border_radius="full",
            box_shadow="var(--shadow-4)",
            title="Toggle AI Copilot (Ctrl+K)",
        ),
    )
