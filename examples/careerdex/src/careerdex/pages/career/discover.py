from __future__ import annotations

from typing import Any

import reflex as rx

from careerdex.components.layout import page_shell, skeleton_card
from careerdex.state.career import CareerState


def _company_avatar(company: rx.Var[str]) -> rx.Component:
    return rx.box(
        rx.text(
            rx.cond(company.length() > 0, company[0:1].upper(), "?"),  # type: ignore[index]
            size="3",
            weight="bold",
            color="white",
        ),
        width="48px",
        height="48px",
        min_width="48px",
        border_radius="var(--radius-3)",
        background="linear-gradient(135deg, var(--blue-8), var(--blue-10))",
        display="flex",
        align_items="center",
        justify_content="center",
        flex_shrink="0",
        box_shadow="0 2px 6px rgba(3,105,161,0.2)",
    )


def _job_card(job: dict[str, Any]) -> rx.Component:
    return rx.box(
        rx.hstack(
            _company_avatar(job["company"].to(str)),
            rx.vstack(
                rx.hstack(
                    rx.heading(
                        job["title"],
                        size="3",
                        weight="medium",
                        color="var(--gray-12)",
                        _hover={"color": "var(--blue-10)"},
                    ),
                    rx.spacer(),
                    rx.cond(
                        job["posted_date"].to(str) != "",
                        rx.text(job["posted_date"].to(str)[0:10], size="1", color="var(--gray-9)"),
                        rx.text("Recent", size="1", color="var(--gray-9)"),
                    ),
                    align="center",
                    width="100%",
                ),
                rx.hstack(
                    rx.icon("building-2", size=13, color="var(--gray-9)"),
                    rx.text(
                        job["company"],
                        size="2",
                        color="var(--gray-10)",
                        weight="medium",
                    ),
                    rx.text("·", size="2", color="var(--gray-6)"),
                    rx.icon("map-pin", size=13, color="var(--gray-9)"),
                    rx.text(job["location"], size="2", color="var(--gray-10)"),
                    spacing="1",
                    align="center",
                    flex_wrap="wrap",
                ),
                rx.hstack(
                    rx.badge(
                        job["employment_type"],
                        color_scheme="blue",
                        variant="soft",
                        size="1",
                    ),
                    rx.cond(
                        job["salary_max"].to(int) > 0,
                        rx.badge(
                            "$"
                            + job["salary_min"].to(int).to_string()
                            + "–$"
                            + job["salary_max"].to(int).to_string(),
                            color_scheme="green",
                            variant="soft",
                            size="1",
                        ),
                        rx.badge("Salary TBD", color_scheme="gray", variant="soft", size="1"),
                    ),
                    rx.cond(
                        job["remote"],
                        rx.badge("Remote", color_scheme="purple", variant="soft", size="1"),
                        rx.fragment(),
                    ),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                spacing="2",
                align="start",
                flex="1",
                min_width="0",
            ),
            rx.vstack(
                rx.button(
                    "Quick Apply",
                    size="2",
                    color_scheme="blue",
                    border_radius="20px",
                    min_width="110px",
                    cursor="pointer",
                ),
                rx.icon_button(
                    rx.icon("bookmark", size=14),
                    variant="ghost",
                    size="2",
                    color_scheme="gray",
                    cursor="pointer",
                ),
                align="center",
                flex_shrink="0",
                spacing="1",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        padding="5",
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        width="100%",
        cursor="pointer",
        _hover={
            "border_color": "var(--blue-6)",
            "box_shadow": "0 2px 16px rgba(3,105,161,0.09)",
            "transform": "translateY(-1px)",
        },
        transition="all 0.15s ease",
    )


def _checkbox_row(label: str) -> rx.Component:
    return rx.hstack(
        rx.checkbox(size="2", color_scheme="blue"),
        rx.text(label, size="2", color="var(--gray-11)"),
        spacing="2",
        align="center",
        cursor="pointer",
    )


def _filter_section(title: str, items: list[str]) -> rx.Component:
    return rx.vstack(
        rx.text(title, size="2", weight="bold", color="var(--gray-12)"),
        *[_checkbox_row(item) for item in items],
        spacing="2",
        align="start",
        width="100%",
        padding_bottom="4",
        border_bottom="1px solid var(--gray-4)",
    )


def _filter_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("sliders-horizontal", size=14, color="var(--blue-9)"),
                    rx.text("Filters", size="3", weight="bold", color="var(--gray-12)"),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                rx.button("Clear all", size="1", variant="ghost", color_scheme="gray"),
                align="center",
                width="100%",
                margin_bottom="2",
            ),
            _filter_section("Job Type", ["Full-time", "Contract", "Part-time", "Internship"]),
            _filter_section(
                "Experience Level", ["Entry Level", "Mid Level", "Senior Level", "Lead / Manager"]
            ),
            _filter_section("Work Mode", ["Remote", "Hybrid", "On-site"]),
            _filter_section("Salary Range", ["$50k–$80k", "$80k–$120k", "$120k–$160k", "$160k+"]),
            rx.vstack(
                rx.text("Skills / Tech", size="2", weight="bold", color="var(--gray-12)"),
                rx.flex(
                    *[
                        rx.badge(
                            s, color_scheme="blue", variant="outline", size="1", cursor="pointer"
                        )
                        for s in ["Python", "SQL", "Spark", "AWS", "dbt", "Airflow"]
                    ],
                    gap="2",
                    flex_wrap="wrap",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        padding="5",
        width="230px",
        min_width="230px",
        position="sticky",
        top="calc(64px + 24px)",
        align_self="flex-start",
        flex_shrink="0",
    )


def discover_page() -> rx.Component:
    return page_shell(
        "Discover Jobs",
        rx.vstack(
            # Job Channels Section
            rx.vstack(
                rx.hstack(
                    rx.icon("layers", size=16, color="var(--blue-9)"),
                    rx.text("Job Channels", size="3", weight="bold", color="var(--gray-12)"),
                    rx.spacer(),
                    rx.text(
                        "Filter by source",
                        size="2",
                        color="var(--gray-9)",
                    ),
                    align="center",
                ),
                rx.flex(
                    rx.card(
                        rx.hstack(
                            rx.icon("layers", size=16, color="var(--blue-9)"),
                            rx.text("All Sources", size="2", weight="medium"),
                            rx.spacer(),
                            rx.text("Click to filter", size="1", color="var(--gray-9)"),
                            spacing="2",
                            align="center",
                        ),
                        padding="4",
                        min_width="120px",
                        cursor="pointer",
                        on_click=lambda: CareerState.load_jobs(),
                    ),
                    gap="3",
                    flex_wrap="wrap",
                ),
                rx.cond(
                    CareerState.selected_job_source != "",
                    rx.button(
                        "Clear Channel Filter",
                        size="1",
                        variant="ghost",
                        color_scheme="gray",
                        on_click=lambda: CareerState.load_jobs(),
                    ),
                ),
                spacing="3",
                padding="4",
                background="var(--gray-2)",
                border_radius="var(--radius-3)",
                margin_bottom="4",
                width="100%",
            ),
            # Search Bar
            rx.hstack(
                rx.input(
                    placeholder="Search jobs (e.g., 'data engineer', 'remote python')...",
                    on_change=CareerState.set_search_query,
                    width="400px",
                ),
                rx.button(
                    rx.icon("search", size=14),
                    "Search",
                    on_click=lambda: CareerState.search_jobs(),
                    color_scheme="blue",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.icon("briefcase", size=15, color="var(--blue-9)"),
                    rx.text(
                        CareerState.jobs.length(),
                        " cached",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    rx.cond(
                        CareerState.search_results.length() > 0,
                        rx.text(
                            " + " + CareerState.search_results.length().to_string() + " search",
                            size="2",
                            color="var(--teal-10)",
                        ),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    "Refresh",
                    size="2",
                    variant="outline",
                    color_scheme="gray",
                    on_click=lambda: CareerState.load_jobs(),
                ),
                align="center",
                width="100%",
                margin_bottom="4",
            ),
            # Search Results
            rx.cond(
                CareerState.search_results.length() > 0,
                rx.vstack(
                    rx.heading(
                        "Search Results (" + CareerState.search_results.length().to_string() + ")",
                        size="4",
                    ),
                    rx.foreach(CareerState.search_results, _job_card),
                    spacing="3",
                    width="100%",
                ),
            ),
            # Jobs Grid
            rx.hstack(
                _filter_panel(),
                rx.vstack(
                    rx.cond(
                        CareerState.is_loading,
                        rx.vstack(
                            *[skeleton_card() for _ in range(5)],
                            spacing="3",
                            width="100%",
                        ),
                        rx.cond(
                            CareerState.jobs.length() == 0,
                            rx.center(
                                rx.vstack(
                                    rx.box(
                                        rx.icon("search", size=36, color="var(--blue-9)"),
                                        padding="5",
                                        background="var(--blue-2)",
                                        border_radius="50%",
                                        display="flex",
                                        align_items="center",
                                        justify_content="center",
                                    ),
                                    rx.heading(
                                        "No jobs found yet", size="4", color="var(--gray-11)"
                                    ),
                                    rx.text(
                                        "Run a search to populate results, or check back soon.",
                                        size="2",
                                        color="var(--gray-9)",
                                        text_align="center",
                                        max_width="280px",
                                    ),
                                    rx.button(
                                        rx.icon("refresh-cw", size=14),
                                        "Refresh Jobs",
                                        color_scheme="blue",
                                        on_click=lambda: CareerState.load_jobs(),
                                    ),
                                    align="center",
                                    spacing="4",
                                    padding_y="12",
                                ),
                            ),
                            rx.foreach(CareerState.jobs, _job_card),
                        ),
                    ),
                    flex="1",
                    min_width="0",
                    width="100%",
                    spacing="3",
                ),
                spacing="5",
                align="start",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_jobs(),
    )
