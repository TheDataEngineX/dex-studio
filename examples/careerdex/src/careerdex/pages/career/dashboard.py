from __future__ import annotations

from typing import Any

import reflex as rx

from careerdex.components.layout import page_shell, status_badge
from careerdex.state.career import CareerState


def _metric_card(
    icon: str,
    label: str,
    value: rx.Var,
    color: str,
    trend: str = "",
) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=18, color=f"var(--{color}-9)"),
                    padding="8px",
                    background=f"var(--{color}-3)",
                    border_radius="var(--radius-2)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
                rx.spacer(),
                rx.cond(
                    trend != "",
                    rx.badge(trend, color_scheme="green", variant="soft", size="1"),
                    rx.fragment(),
                ),
                align="center",
                width="100%",
            ),
            rx.heading(value, size="7", weight="bold", color="var(--gray-12)"),
            rx.text(label, size="2", color="var(--gray-9)"),
            spacing="2",
            align="start",
        ),
        padding="5",
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        _hover={"box_shadow": "0 2px 10px rgba(0,0,0,0.06)", "border_color": f"var(--{color}-5)"},
        transition="all 0.15s ease",
    )


def _recent_app_row(a: dict[str, Any]) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.box(
                    rx.text(
                        rx.cond(
                            a["company"].to(str) != "",
                            a["company"].to(str)[0:1].upper(),
                            "?",
                        ),
                        size="1",
                        weight="bold",
                        color="white",
                    ),
                    width="28px",
                    height="28px",
                    border_radius="var(--radius-2)",
                    background="var(--blue-9)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    flex_shrink="0",
                ),
                rx.text(a["company"], weight="medium", size="2"),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(rx.text(a["position"], size="2", color="var(--gray-11)")),
        rx.table.cell(status_badge(a["status"])),
        rx.table.cell(
            rx.text(
                a["applied_at"],
                size="1",
                color="var(--gray-9)",
            )
        ),
    )


def _quick_action(icon: str, label: str, href: str, color: str) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.box(
                rx.icon(icon, size=20, color=f"var(--{color}-9)"),
                padding="12px",
                background=f"var(--{color}-3)",
                border_radius="var(--radius-3)",
                display="flex",
                align_items="center",
                justify_content="center",
            ),
            rx.text(label, size="2", weight="medium", color="var(--gray-11)", text_align="center"),
            align="center",
            spacing="2",
        ),
        href=href,
        text_decoration="none",
        padding="4",
        background="white",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        display="flex",
        align_items="center",
        justify_content="center",
        _hover={
            "border_color": f"var(--{color}-5)",
            "box_shadow": "0 2px 8px rgba(0,0,0,0.06)",
            "transform": "translateY(-1px)",
        },
        transition="all 0.15s ease",
    )


def career_dashboard() -> rx.Component:
    return page_shell(
        "Dashboard",
        rx.cond(
            CareerState.error != "",
            rx.callout.root(
                rx.callout.text(CareerState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        # Metric cards
        rx.grid(
            _metric_card("send", "Applications", CareerState.applications_count, "blue", "+12%"),
            _metric_card("message-circle", "Response Rate", CareerState.response_rate, "teal"),
            _metric_card("mic", "Interviews", CareerState.interviews_count, "violet"),
            _metric_card("trophy", "Offers", CareerState.offers_count, "green"),
            columns="4",
            gap="4",
            margin_bottom="6",
        ),
        # Quick actions
        rx.vstack(
            rx.heading(
                "Quick Actions",
                size="3",
                weight="medium",
                color="var(--gray-12)",
                margin_bottom="3",
            ),
            rx.grid(
                _quick_action("search", "Find Jobs", "/discover", "blue"),
                _quick_action("file-text", "Resume", "/resume", "indigo"),
                _quick_action("shuffle", "Matcher", "/resume-matcher", "violet"),
                _quick_action("mic", "Interview Prep", "/interview", "orange"),
                _quick_action("handshake", "Negotiate", "/negotiate", "green"),
                _quick_action("trending-up", "Progress", "/progress", "teal"),
                columns="6",
                gap="3",
                width="100%",
            ),
            margin_bottom="6",
            width="100%",
            align="start",
        ),
        # Recent applications
        rx.vstack(
            rx.hstack(
                rx.heading(
                    "Application Pipeline", size="3", weight="medium", color="var(--gray-12)"
                ),
                rx.spacer(),
                rx.hstack(
                    rx.input(
                        placeholder="Filter by company or role...",
                        on_change=CareerState.set_search_query,
                        width="250px",
                        size="2",
                    ),
                    spacing="2",
                ),
                align="center",
                width="100%",
                margin_bottom="3",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.center(rx.spinner(size="3"), padding_y="8"),
                rx.cond(
                    CareerState.applications.length() == 0,
                    rx.center(
                        rx.vstack(
                            rx.icon("inbox", size=36, color="var(--gray-6)"),
                            rx.text("No applications yet", weight="medium", color="var(--gray-10)"),
                            rx.text(
                                "Start tracking your job search.", size="2", color="var(--gray-9)"
                            ),
                            rx.link(
                                rx.button("Add Application", size="2", color_scheme="blue"),
                                href="/applications",
                                text_decoration="none",
                            ),
                            align="center",
                            spacing="3",
                            padding_y="8",
                        ),
                    ),
                    rx.box(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("Company"),
                                    rx.table.column_header_cell("Role"),
                                    rx.table.column_header_cell("Status"),
                                    rx.table.column_header_cell("Date"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    CareerState.applications, lambda app: _recent_app_row(app)
                                )
                            ),
                            width="100%",
                        ),
                        background="white",
                        border="1px solid var(--gray-4)",
                        border_radius="var(--radius-3)",
                        overflow="hidden",
                    ),
                ),
            ),
            # Community Stats
            rx.vstack(
                rx.hstack(
                    rx.icon("users", size=16, color="var(--violet-9)"),
                    rx.text("Community Stats", size="3", weight="bold", color="var(--gray-12)"),
                    rx.spacer(),
                    rx.text("DataEngineX Network", size="2", color="var(--gray-9)"),
                    align="center",
                ),
                rx.grid(
                    rx.card(
                        rx.vstack(
                            rx.text("Active Job Seekers", size="1", color="var(--gray-9)"),
                            rx.text("1,247", size="5", weight="bold", color="var(--violet-11)"),
                            rx.text("+12% this week", size="1", color="var(--green-10)"),
                            align="center",
                        ),
                        padding="4",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.text("Avg. Response Rate", size="1", color="var(--gray-9)"),
                            rx.text("34%", size="5", weight="bold", color="var(--blue-11)"),
                            rx.text("Across network", size="1", color="var(--gray-9)"),
                            align="center",
                        ),
                        padding="4",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.text("Top Skills Demand", size="1", color="var(--gray-9)"),
                            rx.text("Python, SQL", size="4", weight="bold", color="var(--teal-11)"),
                            rx.text("in active roles", size="1", color="var(--gray-9)"),
                            align="center",
                        ),
                        padding="4",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.text("Remote-Friendly", size="1", color="var(--gray-9)"),
                            rx.text("68%", size="5", weight="bold", color="var(--green-11)"),
                            rx.text("of all postings", size="1", color="var(--gray-9)"),
                            align="center",
                        ),
                        padding="4",
                    ),
                    columns="4",
                    gap="3",
                    width="100%",
                ),
                spacing="3",
                padding="4",
                background="var(--violet-2)",
                border_radius="var(--radius-3)",
                margin_bottom="6",
                width="100%",
            ),
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
