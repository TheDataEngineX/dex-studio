from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def resume_matcher_page() -> rx.Component:
    return page_shell(
        "Resume Matcher",
        rx.vstack(
            rx.heading("Resume vs Job Description Matcher", size="4"),
            rx.text("Paste your resume and a job description to get AI-powered gap analysis."),
            rx.vstack(
                rx.text("Resume", weight="bold"),
                rx.text_area(
                    placeholder="Paste your resume text here...",
                    on_change=CareerState.set_resume_text,
                    rows="8",
                    width="100%",
                ),
                spacing="2",
            ),
            rx.vstack(
                rx.text("Job Description", weight="bold"),
                rx.text_area(
                    placeholder="Paste the job description here...",
                    on_change=CareerState.set_job_description,
                    rows="8",
                    width="100%",
                ),
                spacing="2",
            ),
            rx.button(
                "Analyze Match",
                on_click=CareerState.match_resume,
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
                CareerState.match_results.length() > 0,
                rx.vstack(
                    rx.heading("Match Results", size="5", weight="bold"),
                    rx.foreach(
                        CareerState.match_results,
                        lambda result: rx.callout.root(
                            rx.vstack(
                                rx.text(f"Score: {result.get('overall_score', 'N/A')}%"),
                                rx.text(f"Missing: {result.get('missing_skills', [])}"),
                            ),
                            color_scheme="green",
                        ),
                    ),
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
