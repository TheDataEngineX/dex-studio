from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def pipeline_page() -> rx.Component:
    return page_shell(
        "Auto-Pipeline",
        rx.vstack(
            rx.heading("Job URL Pipeline", size="5", margin_bottom="4"),
            rx.text("Paste a job URL to run: evaluate → match → cover letter → tracker."),
            rx.vstack(
                rx.text("Job URL", weight="bold"),
                rx.input(
                    placeholder="https://careers.company.com/jobs/12345",
                    width="100%",
                ),
                spacing="2",
            ),
            rx.hstack(
                rx.button("Run Pipeline", color_scheme="blue"),
                rx.button("Add to Batch", on_click=CareerState.add_batch_job, color_scheme="teal"),
                spacing="2",
            ),
            rx.callout.root(
                rx.vstack(
                    rx.text("Pipeline Steps:", weight="bold"),
                    rx.text("1. Job Evaluation (score & grade)"),
                    rx.text("2. Resume Match Analysis"),
                    rx.text("3. Cover Letter Generation"),
                    rx.text("4. Add to Application Tracker"),
                ),
                color_scheme="gray",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
