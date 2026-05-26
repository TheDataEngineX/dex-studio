from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell, skeleton_card
from careerdex.state.jobs import JobsState


def _source_badge(source: str) -> rx.Component:
    return rx.badge(
        source,
        color_scheme="blue",
        variant="soft",
        size="1",
    )


def _company_avatar() -> rx.Component:
    return rx.box(
        rx.text("?", size="3", weight="bold", color="white"),
        width="48px",
        height="48px",
        min_width="48px",
        border_radius="var(--radius-3)",
        background="linear-gradient(135deg, var(--blue-8), var(--blue-10))",
        display="flex",
        align_items="center",
        justify_content="center",
        flex_shrink=0,
    )


def _job_card(job: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            _company_avatar(),
            rx.vstack(
                rx.hstack(
                    rx.heading("Job Title", size="3", weight="medium", color="var(--gray-12)"),
                    rx.spacer(),
                    rx.text("date", size="1", color="var(--gray-9)"),
                    align="center",
                    width="100%",
                ),
                rx.hstack(
                    rx.icon("building-2", size=13, color="var(--gray-9)"),
                    rx.text("Company Name", size="2", color="var(--gray-10)", weight="medium"),
                    rx.text("·", size="2", color="var(--gray-6)"),
                    rx.icon("map-pin", size=13, color="var(--gray-9)"),
                    rx.text("Location", size="2", color="var(--gray-10)"),
                    spacing="1",
                    align="center",
                    flex_wrap="wrap",
                ),
                rx.hstack(
                    _source_badge("Source"),
                    rx.badge("Salary", color_scheme="green", variant="soft", size="1"),
                    rx.badge("Remote", color_scheme="purple", variant="soft", size="1"),
                    spacing="2",
                    flex_wrap="wrap",
                ),
                spacing="2",
                align="start",
                flex="1",
                min_width="0",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        padding="4",
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        width="100%",
        cursor="pointer",
        _hover={
            "border_color": "var(--blue-6)",
            "box_shadow": "0 2px 16px rgba(3,105,161,0.09)",
        },
        on_click=lambda: JobsState.select_job(job),
    )


def _sidebar_filters() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Filters", size="3", weight="bold", color="var(--gray-12)"),
            rx.input(
                placeholder="Search jobs...",
                on_change=JobsState.set_query,
                value=JobsState.query,
            ),
            rx.input(
                placeholder="Location",
                on_change=JobsState.set_location,
                value=JobsState.location,
            ),
            rx.checkbox(
                "Remote only",
                checked=JobsState.remote_only,
                on_change=JobsState.set_remote_only,
            ),
            rx.text("Sources", size="2", weight="bold", color="var(--gray-12)", margin_top="3"),
            rx.vstack(
                rx.checkbox("LinkedIn", default_checked=True),
                rx.checkbox("Indeed", default_checked=True),
                rx.checkbox("Greenhouse", default_checked=True),
                rx.checkbox("Lever", default_checked=True),
                rx.checkbox("Workday", default_checked=True),
                spacing="1",
                align="start",
            ),
            rx.button(
                rx.icon("search", size=14),
                "Search",
                on_click=lambda: JobsState.do_search(),
                color_scheme="blue",
                width="100%",
                margin_top="3",
            ),
            rx.button(
                rx.icon("refresh-cw", size=14),
                "Refresh All",
                on_click=lambda: JobsState.refresh_all(),
                variant="outline",
                color_scheme="gray",
                width="100%",
            ),
            spacing="3",
            align="stretch",
            width="100%",
        ),
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        padding="4",
        width="240px",
        min_width="240px",
        position="sticky",
        top="calc(64px + 24px)",
        align_self="flex-start",
        flex_shrink=0,
    )


def _job_detail_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("Select a job", size="4", weight="bold", color="var(--gray-12)"),
            rx.hstack(
                rx.icon("building-2", size=14, color="var(--gray-9)"),
                rx.text("Company", size="2", weight="medium", color="var(--gray-11)"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                rx.icon("map-pin", size=14, color="var(--gray-9)"),
                rx.text("Location", size="2", color="var(--gray-11)"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                _source_badge("Source"),
                rx.text("Posted: recent", size="1", color="var(--gray-9)"),
                spacing="2",
                align="center",
                flex_wrap="wrap",
            ),
            rx.divider(),
            rx.text(
                "Job description will appear here...",
                size="2",
                color="var(--gray-11)",
            ),
            rx.hstack(
                rx.button(
                    rx.icon("external-link", size=14),
                    "Apply",
                    color_scheme="blue",
                ),
                rx.button(
                    rx.icon("bookmark", size=14),
                    "Save",
                    variant="outline",
                    color_scheme="gray",
                ),
                spacing="3",
                margin_top="4",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        padding="5",
        width="100%",
        min_width="320px",
        position="sticky",
        top="calc(64px + 24px)",
        align_self="flex-start",
        flex_shrink=0,
    )


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.box(
                rx.icon("briefcase", size=36, color="var(--blue-9)"),
                padding="5",
                background="var(--blue-2)",
                border_radius="50%",
                display="flex",
                align_items="center",
                justify_content="center",
            ),
            rx.heading("No jobs found", size="4", color="var(--gray-11)"),
            rx.text(
                "Search jobs or refresh to load new listings",
                size="2",
                color="var(--gray-9)",
                text_align="center",
            ),
            align="center",
            spacing="4",
            padding_y="12",
        ),
        min_height="300px",
    )


def jobs_page() -> rx.Component:
    return page_shell(
        "Jobs",
        rx.hstack(
            _sidebar_filters(),
            rx.box(
                rx.vstack(
                    rx.cond(
                        JobsState.is_loading,
                        rx.vstack(
                            *[skeleton_card() for _ in range(5)],
                            spacing="3",
                            width="100%",
                        ),
                    ),
                    rx.cond(
                        ~JobsState.is_loading,
                        rx.cond(
                            JobsState.results.length() == 0,
                            _empty_state(),
                            rx.vstack(
                                rx.heading(
                                    "Results",
                                    size="3",
                                    weight="bold",
                                    color="var(--gray-12)",
                                ),
                                rx.foreach(JobsState.results, _job_card),
                                spacing="3",
                                width="100%",
                            ),
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                flex="1",
                min_width="0",
            ),
            rx.cond(
                JobsState.selected_job.length() > 0,
                _job_detail_panel(),
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
    )
