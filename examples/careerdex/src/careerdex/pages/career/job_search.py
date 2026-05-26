from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _job_row(job: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(job["title"], weight="bold")),
        rx.table.cell(job["company"]),
        rx.table.cell(job.get("location", "—")),
        rx.table.cell(
            rx.badge(job.get("source", "web"), color_scheme="gray"),
        ),
    )


def job_search_page() -> rx.Component:
    return page_shell(
        "Job Search",
        rx.hstack(
            rx.heading("Job Search", size="5"),
            rx.spacer(),
            rx.button("Refresh", on_click=CareerState.load_jobs, size="2"),
            margin_bottom="4",
        ),
        rx.cond(CareerState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            CareerState.error != "",
            rx.callout.root(
                rx.callout.text(CareerState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CareerState.jobs.length() == 0,
            rx.callout.root(
                rx.callout.text("No jobs found. Configure job sources in dex.yaml."),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Title"),
                        rx.table.column_header_cell("Company"),
                        rx.table.column_header_cell("Location"),
                        rx.table.column_header_cell("Source"),
                    )
                ),
                rx.table.body(rx.foreach(CareerState.jobs, _job_row)),
            ),
        ),
        on_mount=CareerState.load_jobs,
    )
