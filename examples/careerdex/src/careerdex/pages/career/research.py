from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def research_page() -> rx.Component:
    return page_shell(
        "Company Research",
        rx.vstack(
            rx.heading("Company Research", size="4"),
            rx.text("Deep LLM-powered research on companies."),
            rx.hstack(
                rx.input(
                    placeholder="Company name (e.g., Databricks)",
                    on_change=CareerState.set_research_company,
                    width="300px",
                ),
                rx.button(
                    "Research",
                    on_click=CareerState.do_research,
                    color_scheme="blue",
                ),
                spacing="2",
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
                CareerState.research_result.length() > 0,
                rx.card(
                    rx.heading(CareerState.research_result.get("name", ""), size="5"),
                    rx.text(CareerState.research_result.get("description", "")),
                    rx.hstack(
                        rx.text(
                            f"Industry: {CareerState.research_result.get('industry', 'N/A')}",
                            size="2",
                        ),
                        rx.text(
                            f"Size: {CareerState.research_result.get('size', 'N/A')}", size="2"
                        ),
                    ),
                    padding="4",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_jobs,
    )
