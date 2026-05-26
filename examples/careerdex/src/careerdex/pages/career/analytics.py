from __future__ import annotations

from typing import Any

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _stat_card(label: str, value: Any) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(label, size="2", color_scheme="gray"),
            rx.text(str(value), size="5", weight="bold"),
            spacing="1",
        ),
        padding="4",
    )


def _funnel_bar(label: str, count: rx.Var, total: rx.Var, color: str) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="2", width="80px"),
        rx.box(
            rx.box(width="50%", background=color, height="20px", border_radius="var(--radius-2)"),
            width="200px",
            background="var(--gray-3)",
            border_radius="var(--radius-2)",
        ),
        rx.text(count.to_string(), size="2", weight="medium"),
        spacing="2",
        align="center",
    )


def analytics_page() -> rx.Component:
    return page_shell(
        "Analytics",
        rx.vstack(
            rx.grid(
                _stat_card("Applications", CareerState.applications_count),
                _stat_card("Response Rate", CareerState.response_rate),
                _stat_card("Interviews", CareerState.interviews_count),
                _stat_card("Offers", CareerState.offers_count),
                columns="4",
                gap="4",
                margin_bottom="6",
            ),
            rx.heading("Application Funnel", size="4", margin_bottom="3"),
            rx.cond(
                CareerState.applications.length() > 0,
                rx.vstack(
                    _funnel_bar(
                        "Applied",
                        CareerState.applications.length(),
                        CareerState.applications.length(),
                        "var(--blue-8)",
                    ),
                    _funnel_bar(
                        "Responded",
                        CareerState.applications.length(),
                        CareerState.applications.length(),
                        "var(--teal-8)",
                    ),
                    _funnel_bar(
                        "Interview",
                        CareerState.interviews_count,
                        CareerState.applications.length(),
                        "var(--violet-8)",
                    ),
                    _funnel_bar(
                        "Offers",
                        CareerState.offers_count,
                        CareerState.applications.length(),
                        "var(--green-8)",
                    ),
                ),
                rx.callout.root(rx.callout.text("No applications yet"), color_scheme="gray"),
            ),
            spacing="3",
        ),
        rx.cond(
            CareerState.is_loading,
            rx.spinner(),
            rx.fragment(),
        ),
        on_mount=CareerState.compute_funnel,
    )
