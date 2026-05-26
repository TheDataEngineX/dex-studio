from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def projects_page() -> rx.Component:
    return page_shell(
        "Portfolio Projects",
        rx.vstack(
            rx.heading("AI Project Portfolio Evaluation", size="5", margin_bottom="4"),
            rx.text("Evaluate your portfolio projects for job applications."),
            rx.vstack(
                rx.text("Project Description", weight="bold"),
                rx.text_area(
                    placeholder="Describe your project...",
                    rows="6",
                    width="100%",
                ),
                spacing="2",
            ),
            rx.vstack(
                rx.text("Target Role", weight="bold"),
                rx.input(placeholder="e.g., Senior Data Engineer"),
                spacing="2",
            ),
            rx.button("Evaluate Project", color_scheme="blue"),
            rx.heading("Your Projects", size="4", margin_top="4"),
            rx.callout.root(
                rx.callout.text("Add projects to track your portfolio impact."),
                color_scheme="gray",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
