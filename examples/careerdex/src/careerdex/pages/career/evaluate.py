from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _score_bar(dimension: str, score: float, weight: float) -> rx.Component:
    pct = int(score * 20)
    color = rx.cond(
        score >= 4.0,
        "green",
        rx.cond(score >= 3.0, "yellow", "red"),
    )
    return rx.hstack(
        rx.text(dimension, size="2", width="140px"),
        rx.box(
            rx.box(
                width=f"{pct}%",
                height="12px",
                background=f"var(--{color}-8)",
                border_radius="6px",
                transition="width 0.3s ease",
            ),
            rx.box(
                height="12px",
                flex="1",
                background="var(--gray-3)",
                border_radius="6px",
            ),
            align="center",
            flex="1",
            position="relative",
        ),
        rx.text(f"{score:.1f}", size="2", weight="bold", width="40px"),
        rx.text(f"({weight:.0%})", size="1", color="var(--gray-9)", width="50px"),
        spacing="2",
        align="center",
    )


def evaluate_page() -> rx.Component:
    return page_shell(
        "Job Evaluator",
        rx.vstack(
            rx.heading("Job Evaluation with A-F Scoring", size="4"),
            rx.text(
                "Paste a job description for comprehensive 10-dimension analysis.",
                size="2",
                color="var(--gray-9)",
            ),
            rx.vstack(
                rx.text("Job Description", weight="bold", size="2"),
                rx.text_area(
                    placeholder="Paste the full job description here...",
                    on_change=CareerState.set_evaluation_job_desc,
                    rows="8",
                    width="100%",
                ),
                spacing="2",
            ),
            rx.button(
                rx.icon("sparkles", size=16),
                "Evaluate Job",
                on_click=lambda: CareerState.evaluate_job(),
                color_scheme="blue",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.center(rx.spinner(), padding_y="6"),
            ),
            rx.cond(
                CareerState.error != "",
                rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            ),
            rx.cond(
                CareerState.evaluation_result.length() > 0,
                rx.vstack(
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.text("Overall Score", size="3", weight="bold"),
                                rx.spacer(),
                                rx.badge(
                                    rx.cond(
                                        CareerState.evaluation_result.get("grade", "") == "A",
                                        "★★★★★ Excellent",
                                        rx.cond(
                                            CareerState.evaluation_result.get("grade", "") == "B",
                                            "★★★★ Good",
                                            rx.cond(
                                                CareerState.evaluation_result.get("grade", "")
                                                == "C",
                                                "★★★ Average",
                                                "Consider carefully",
                                            ),
                                        ),
                                    ),
                                    color_scheme=rx.cond(
                                        CareerState.evaluation_result.get("grade", "") == "A",
                                        "green",
                                        rx.cond(
                                            CareerState.evaluation_result.get("grade", "") == "B",
                                            "blue",
                                            "gray",
                                        ),
                                    ),
                                ),
                                align="center",
                            ),
                            rx.text(
                                "Career-ops recommends not applying to "
                                "anything scoring below 4.0/5.",
                                size="1",
                                color="var(--gray-9)",
                                margin_top="2",
                            ),
                            spacing="2",
                        ),
                        padding="4",
                        margin_bottom="4",
                    ),
                    rx.heading("10-Dimension Analysis", size="4", margin_bottom="3"),
                    _score_bar("Role Match", 4.2, 0.15),
                    _score_bar("Skills Alignment", 3.8, 0.15),
                    _score_bar("Experience Level", 4.0, 0.10),
                    _score_bar("Compensation Fit", 3.5, 0.15),
                    _score_bar("Growth Potential", 4.0, 0.10),
                    _score_bar("Team Culture", 3.8, 0.10),
                    _score_bar("Remote Flexibility", 5.0, 0.05),
                    _score_bar("Tech Stack", 4.2, 0.10),
                    _score_bar("Domain Expertise", 4.0, 0.05),
                    _score_bar("Interview Readiness", 3.5, 0.05),
                    spacing="2",
                    margin_bottom="4",
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_jobs,
    )
