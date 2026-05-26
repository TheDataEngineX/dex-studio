from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def apply_page() -> rx.Component:
    return page_shell(
        "Apply",
        rx.heading("Apply Mode", size="5", margin_bottom="4"),
        rx.vstack(
            rx.heading("AI-Powered Application Form Filling", size="4"),
            rx.text("Automatically fill job application forms using your resume data."),
            rx.vstack(
                rx.text("Job Posting URL", weight="bold"),
                rx.input(placeholder="https://careers.company.com/jobs/12345"),
                spacing="2",
            ),
            rx.vstack(
                rx.text("Company Name", weight="bold"),
                rx.input(placeholder="e.g., Databricks"),
                spacing="2",
            ),
            rx.vstack(
                rx.text("Position", weight="bold"),
                rx.input(placeholder="e.g., Senior Data Engineer"),
                spacing="2",
            ),
            rx.button("Auto-Fill Form", color_scheme="blue"),
            rx.callout.root(
                rx.callout.text(
                    "This feature requires browser integration. "
                    "Use the CLI for now: dex career apply --url <url>"
                ),
                color_scheme="gray",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
