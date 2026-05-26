from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _story_card(s: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("message-circle", size=14, color="var(--blue-9)"),
                rx.text(s.get("title", "Untitled Story"), size="3", weight="bold"),
                rx.spacer(),
                rx.badge(s.get("category", "General"), color_scheme="blue", variant="soft"),
                spacing="2",
                align="center",
            ),
            rx.divider(),
            rx.vstack(
                rx.hstack(
                    rx.text("Situation", size="1", weight="bold", color="var(--blue-10)"),
                    rx.text("(S)", size="1", color="var(--gray-6)"),
                    align="center",
                ),
                rx.text(s.get("situation", ""), size="2", color="var(--gray-11)"),
                rx.hstack(
                    rx.text("Task", size="1", weight="bold", color="var(--blue-10)"),
                    rx.text("(T)", size="1", color="var(--gray-6)"),
                    align="center",
                ),
                rx.text(s.get("task", ""), size="2", color="var(--gray-11)"),
                rx.hstack(
                    rx.text("Action", size="1", weight="bold", color="var(--blue-10)"),
                    rx.text("(A)", size="1", color="var(--gray-6)"),
                    align="center",
                ),
                rx.text(s.get("action", ""), size="2", color="var(--gray-11)"),
                rx.hstack(
                    rx.text("Result", size="1", weight="bold", color="var(--green-10)"),
                    rx.text("(R)", size="1", color="var(--gray-6)"),
                    align="center",
                ),
                rx.text(s.get("result", ""), size="2", weight="medium", color="var(--gray-12)"),
                spacing="2",
                align="start",
            ),
            rx.cond(
                s.get("reflection", ""),
                rx.box(
                    rx.hstack(
                        rx.icon("lightbulb", size=14, color="var(--yellow-10)"),
                        rx.text("Reflection", size="1", weight="bold", color="var(--yellow-10)"),
                        rx.text("(+R)", size="1", color="var(--gray-6)"),
                        align="center",
                    ),
                    rx.text(s.get("reflection", ""), size="2", color="var(--gray-10)"),
                    background="var(--yellow-2)",
                    padding="3",
                    border_radius="var(--radius-2)",
                    margin_top="2",
                ),
            ),
            spacing="3",
        ),
        padding="4",
        margin_bottom="3",
        border="1px solid var(--gray-4)",
        _hover={"border_color": "var(--blue-6)"},
        transition="all 0.15s ease",
    )


def stories_page() -> rx.Component:
    return page_shell(
        "Story Bank",
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("STAR+R Interview Stories", size="5", weight="bold"),
                    rx.text(
                        "Build your story bank using the STAR+Reflection framework. "
                        "5-10 master stories that answer any behavioral question.",
                        size="2",
                        color="var(--gray-9)",
                    ),
                    align="start",
                ),
                rx.spacer(),
                rx.vstack(
                    rx.button(
                        rx.icon("plus", size=14),
                        "New Story",
                        color_scheme="blue",
                    ),
                    rx.button(
                        "Practice Mode",
                        variant="outline",
                        color_scheme="purple",
                    ),
                    spacing="2",
                ),
                align="center",
                width="100%",
            ),
            rx.card(
                rx.hstack(
                    rx.icon("info", size=14, color="var(--blue-9)"),
                    rx.text(
                        "Career-Ops Tip: The best stories are specific, measurable, "
                        "and demonstrate impact. Include quantifiable results (%, $, time saved).",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                    align="center",
                ),
                background="var(--blue-2)",
                padding="3",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.center(rx.spinner(), padding_y="6"),
            ),
            rx.cond(
                CareerState.error != "",
                rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            ),
            rx.cond(
                CareerState.story_bank.length() > 0,
                rx.vstack(
                    rx.hstack(
                        rx.text(
                            f"Your Story Bank ({CareerState.story_bank.length()})",
                            size="3",
                            weight="bold",
                        ),
                        rx.spacer(),
                        rx.text("5-10 stories recommended", size="2", color="var(--gray-9)"),
                        align="center",
                    ),
                    rx.flex(
                        rx.foreach(CareerState.story_bank, _story_card),
                        gap="4",
                        flex_wrap="wrap",
                        width="100%",
                    ),
                    spacing="4",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("book-open", size=48, color="var(--gray-6)"),
                        rx.heading("No stories yet", size="4", color="var(--gray-10)"),
                        rx.text(
                            "Build your story bank to ace behavioral interviews.",
                            size="2",
                            color="var(--gray-9)",
                        ),
                        rx.button(
                            "Add Your First Story",
                            color_scheme="blue",
                        ),
                        spacing="4",
                        align="center",
                    ),
                    padding_y="12",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_story_bank,
    )
