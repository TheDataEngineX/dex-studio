from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def prep_page() -> rx.Component:
    return page_shell(
        "Prep Hub",
        rx.grid(
            rx.card(
                rx.heading("Interview Prep", size="3", margin_bottom="2"),
                rx.text("Practice questions with AI scoring", size="2", color_scheme="gray"),
                padding="4",
            ),
            rx.card(
                rx.heading("Stories", size="3", margin_bottom="2"),
                rx.text("STAR+Reflection story bank", size="2", color_scheme="gray"),
                padding="4",
            ),
            rx.card(
                rx.heading("Negotiation", size="3", margin_bottom="2"),
                rx.text("Salary negotiation scripts", size="2", color_scheme="gray"),
                padding="4",
            ),
            columns="3",
            gap="4",
        ),
        on_mount=CareerState.load_applications,
    )
