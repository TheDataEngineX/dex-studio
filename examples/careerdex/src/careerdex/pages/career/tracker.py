from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState

_STATUSES = ["applied", "screening", "interview", "offer", "rejected", "withdrawn"]


def _status_filter() -> rx.Component:
    return rx.hstack(
        rx.text("Filter:", size="2", color="gray"),
        rx.select(
            _STATUSES,
            placeholder="All statuses",
            on_change=CareerState.set_search_query,
            width="180px",
        ),
        spacing="2",
        margin_bottom="4",
    )


def _applications_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Company"),
                rx.table.column_header_cell("Role"),
                rx.table.column_header_cell("Status"),
                rx.table.column_header_cell("Applied"),
                rx.table.column_header_cell("Next Step"),
            )
        ),
        rx.table.body(
            rx.foreach(
                CareerState.applications,
                lambda a: rx.table.row(
                    rx.table.cell(a.get("company", "")),
                    rx.table.cell(a.get("position", "")),
                    rx.table.cell(rx.badge(a.get("status", "applied"), color_scheme="blue")),
                    rx.table.cell(a.get("applied_date", "")),
                    rx.table.cell(a.get("next_step", "—")),
                ),
            )
        ),
    )


def tracker_page() -> rx.Component:
    return page_shell(
        "Job Tracker",
        rx.heading("Application Tracker", size="5", margin_bottom="4"),
        _status_filter(),
        rx.cond(
            CareerState.is_loading,
            rx.spinner(size="3"),
            _applications_table(),
        ),
        rx.cond(
            CareerState.error != "",
            rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            rx.fragment(),
        ),
        on_mount=CareerState.load_applications,
    )
