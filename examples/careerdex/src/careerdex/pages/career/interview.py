from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _question_card(q: dict) -> rx.Component:
    return rx.card(
        rx.text(q.get("question", ""), weight="medium", size="3"),
        rx.hstack(
            rx.text(f"Category: {q.get('category', 'General')}", size="1", color="gray"),
            rx.spacer(),
            rx.text(f"Difficulty: {q.get('difficulty', 'medium')}", size="1", color="gray"),
        ),
        padding="4",
        margin_bottom="3",
    )


def interview_page() -> rx.Component:
    return page_shell(
        "Interview Prep",
        rx.vstack(
            rx.heading("Interview Questions", size="4"),
            rx.text("Practice questions for your target role."),
            rx.button(
                "Load Questions",
                on_click=lambda: CareerState.load_interview_questions(),
                color_scheme="blue",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.spinner(),
            ),
            rx.cond(
                CareerState.error != "",
                rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            ),
            rx.cond(
                CareerState.interview_questions.length() > 0,
                rx.vstack(
                    rx.foreach(
                        CareerState.interview_questions[:10],
                        _question_card,
                    ),
                ),
                rx.callout.root(
                    rx.callout.text("Click 'Load Questions' to get started."),
                    color_scheme="gray",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_interview_questions,
    )
