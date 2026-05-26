from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def resume_page() -> rx.Component:
    return page_shell(
        "Resume Builder",
        rx.vstack(
            rx.heading("Your Resume", size="5", margin_bottom="4"),
            rx.vstack(
                rx.text("Paste your resume text below:", weight="bold"),
                rx.text_area(
                    placeholder="Paste resume content...",
                    on_change=CareerState.set_resume_text,
                    rows="15",
                    width="100%",
                ),
                rx.button("Save Resume", color_scheme="blue"),
                spacing="3",
            ),
            rx.heading("Quick Actions", size="4", margin_top="4"),
            rx.hstack(
                rx.link(
                    rx.button("Match to Job", href="/resume-matcher"),
                    href="/resume-matcher",
                ),
                rx.link(
                    rx.button("Generate Cover Letter", href="/cover-letter"),
                    href="/cover-letter",
                ),
                rx.link(
                    rx.button("Export PDF", href="/pdf-export"),
                    href="/pdf-export",
                ),
                spacing="2",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
