from __future__ import annotations

from typing import Any

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _stat_card(label: str, value: Any, color: str) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(str(value), size="5", weight="bold", color="var(--gray-12)"),
            rx.text(label, size="2", color="var(--gray-9)"),
            spacing="0",
            align="start",
        ),
        padding="3",
    )


def _app_row(app: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(app.get("company", ""), weight="bold")),
        rx.table.cell(app.get("position", "")),
        rx.table.cell(rx.badge(app.get("status", "saved"), color_scheme="blue")),
        rx.table.cell(app.get("salary_max", "—")),
        rx.table.cell(app.get("applied_at", "—")),
        cursor="pointer",
        _hover={"background": "var(--gray-2)"},
        on_click=lambda a=app: CareerState.select_application(a.get("id", "")),
    )


def applications_page() -> rx.Component:
    return page_shell(
        "Applications",
        rx.vstack(
            rx.heading("Applications", size="5", weight="bold"),
            rx.hstack(
                _stat_card("Total", CareerState.applications_count, "blue"),
                _stat_card("Interviews", CareerState.interviews_count, "yellow"),
                _stat_card("Offers", CareerState.offers_count, "green"),
                _stat_card("Response", CareerState.response_rate, "violet"),
                rx.spacer(),
                rx.button("Refresh", on_click=CareerState.load_applications, size="2"),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(),
            rx.cond(
                CareerState.applications.length() == 0,
                rx.center(
                    rx.vstack(
                        rx.icon("inbox", size=48, color="var(--gray-6)"),
                        rx.text("No applications tracked yet", weight="medium", size="3"),
                        rx.text(
                            "Search for jobs and start tracking.", size="2", color="var(--gray-9)"
                        ),
                        rx.link(
                            rx.button("Find Jobs", color_scheme="blue"),
                            href="/jobs",
                            text_decoration="none",
                        ),
                        spacing="3",
                        align="center",
                        padding_y="8",
                    ),
                ),
                rx.hstack(
                    rx.vstack(
                        rx.heading(
                            "All Applications", size="3", weight="medium", margin_bottom="3"
                        ),
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("Company"),
                                    rx.table.column_header_cell("Role"),
                                    rx.table.column_header_cell("Status"),
                                    rx.table.column_header_cell("Salary"),
                                    rx.table.column_header_cell("Applied"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(CareerState.applications, _app_row),
                            ),
                        ),
                        spacing="4",
                        align="start",
                        flex="1",
                    ),
                    rx.cond(
                        CareerState.selected_application,
                        rx.card(
                            rx.vstack(
                                rx.hstack(
                                    rx.text(
                                        CareerState.selected_application["company"],
                                        size="4",
                                        weight="bold",
                                    ),
                                    rx.spacer(),
                                    rx.button(
                                        "×",
                                        on_click=lambda: CareerState.select_application(""),
                                        size="1",
                                    ),
                                    align="center",
                                ),
                                rx.text(
                                    CareerState.selected_application["position"],
                                    size="2",
                                    color="var(--gray-10)",
                                ),
                                rx.divider(),
                                rx.hstack(
                                    rx.vstack(
                                        rx.text("Status", size="2", color="var(--gray-9)"),
                                        rx.badge(
                                            CareerState.selected_application["status"],
                                            color_scheme="blue",
                                        ),
                                        spacing="1",
                                    ),
                                    rx.vstack(
                                        rx.text("Salary", size="2", color="var(--gray-9)"),
                                        rx.text(
                                            CareerState.selected_application["salary_max"],
                                            size="2",
                                            weight="medium",
                                        ),
                                        spacing="1",
                                    ),
                                    rx.vstack(
                                        rx.text("Applied", size="2", color="var(--gray-9)"),
                                        rx.text(
                                            CareerState.selected_application["applied_at"], size="2"
                                        ),
                                        spacing="1",
                                    ),
                                    spacing="4",
                                ),
                                rx.cond(
                                    CareerState.selected_application["url"],
                                    rx.link(
                                        rx.button("View Job Posting ↗", size="1", variant="ghost"),
                                        href=CareerState.selected_application["url"],
                                        is_external=True,
                                    ),
                                    rx.fragment(),
                                ),
                                spacing="3",
                                align="start",
                                padding="4",
                            ),
                            width="350px",
                            padding="0",
                        ),
                        rx.fragment(),
                    ),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
