from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def profile_page() -> rx.Component:
    return page_shell(
        "Profile",
        rx.vstack(
            rx.heading("Career Profile", size="5", margin_bottom="4"),
            rx.heading("Your Resume", size="4"),
            rx.text("Paste or update your resume text below."),
            rx.text_area(
                placeholder="Paste your resume here...",
                on_change=CareerState.set_resume_text,
                rows="12",
                width="100%",
            ),
            rx.hstack(
                rx.button("Save Profile", color_scheme="blue"),
                rx.button("Clear", color_scheme="gray"),
                spacing="2",
            ),
            rx.cond(
                CareerState.notification != "",
                rx.callout.root(rx.callout.text(CareerState.notification), color_scheme="green"),
            ),
            rx.heading("Quick Stats", size="4", margin_top="4"),
            rx.hstack(
                rx.card(
                    rx.vstack(
                        rx.text(CareerState.applications_count, size="6", weight="bold"),
                        rx.text("Applications", size="2"),
                    ),
                    padding="4",
                ),
                rx.card(
                    rx.vstack(
                        rx.text(CareerState.interviews_count, size="6", weight="bold"),
                        rx.text("Interviews", size="2"),
                    ),
                    padding="4",
                ),
                rx.card(
                    rx.vstack(
                        rx.text(CareerState.offers_count, size="6", weight="bold"),
                        rx.text("Offers", size="2"),
                    ),
                    padding="4",
                ),
                spacing="2",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
