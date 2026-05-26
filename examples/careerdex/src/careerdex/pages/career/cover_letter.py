from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def cover_letter_page() -> rx.Component:
    return page_shell(
        "Cover Letter",
        rx.vstack(
            rx.heading("Cover Letter Generator", size="4"),
            rx.text("Generate AI-powered personalized cover letters for job applications."),
            rx.grid(
                rx.vstack(
                    rx.text("Company", weight="bold"),
                    rx.input(
                        placeholder="e.g., Databricks",
                        on_change=CareerState.set_cover_letter_company,
                    ),
                    rx.text("Job Title", weight="bold", margin_top="3"),
                    rx.input(
                        placeholder="e.g., Senior Data Engineer",
                        on_change=CareerState.set_cover_letter_job_title,
                    ),
                    spacing="2",
                ),
                rx.vstack(
                    rx.text("Job Description (optional)", weight="bold"),
                    rx.text_area(
                        placeholder="Paste job description for better personalization...",
                        on_change=CareerState.set_job_description,
                        rows="5",
                    ),
                    spacing="2",
                ),
                columns="2",
                gap="4",
            ),
            rx.button(
                "Generate Cover Letter",
                on_click=CareerState.generate_cover_letter,
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
                CareerState.notification != "",
                rx.callout.root(rx.callout.text(CareerState.notification), color_scheme="green"),
            ),
            rx.cond(
                CareerState.cover_letter_result.length() > 0,
                rx.vstack(
                    rx.heading("Generated Cover Letter", size="5", weight="bold", margin_top="4"),
                    rx.box(
                        rx.text(CareerState.cover_letter_result.get("content", "")),
                        padding="4",
                        background="var(--gray-1)",
                        border_radius="var(--radius-3)",
                        white_space="pre-wrap",
                    ),
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
