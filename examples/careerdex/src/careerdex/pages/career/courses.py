from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def courses_page() -> rx.Component:
    return page_shell(
        "Courses",
        rx.vstack(
            rx.heading("Course Recommendations", size="5", margin_bottom="4"),
            rx.text("Find courses to fill skill gaps for your target roles."),
            rx.vstack(
                rx.text("Target Role", weight="bold"),
                rx.input(placeholder="e.g., Senior Data Engineer"),
                spacing="2",
            ),
            rx.vstack(
                rx.text("Skill to Learn", weight="bold"),
                rx.input(placeholder="e.g., Spark, Kubernetes"),
                spacing="2",
            ),
            rx.button("Find Courses", color_scheme="blue"),
            rx.heading("Recommended Courses", size="4", margin_top="4"),
            rx.callout.root(
                rx.callout.text("Courses matching your profile will appear here."),
                color_scheme="gray",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
