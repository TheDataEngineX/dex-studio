from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _metric_card(label: str, value: rx.Var) -> rx.Component:
    return rx.card(
        rx.text(label, size="1", color="gray"),
        rx.heading(value, size="4"),
        padding="4",
    )


def _timeline() -> rx.Component:
    return rx.vstack(
        rx.foreach(
            CareerState.progress_data,
            lambda item: rx.hstack(
                rx.box(
                    width="12px",
                    height="12px",
                    border_radius="50%",
                    background="var(--blue-9)",
                    flex_shrink="0",
                ),
                rx.vstack(
                    rx.text(item.get("event", ""), weight="bold", size="2"),
                    rx.text(item.get("date", ""), size="1", color="gray"),
                    align_items="start",
                    spacing="0",
                ),
                spacing="3",
                align_items="start",
            ),
        ),
        align_items="start",
        spacing="4",
    )


def progress_page() -> rx.Component:
    return page_shell(
        "Progress",
        rx.heading("Progress & Analytics", size="5", margin_bottom="4"),
        rx.grid(
            _metric_card("Applications Sent", CareerState.applications.length()),
            _metric_card("Contacts Made", CareerState.contacts.length()),
            _metric_card("Milestones", CareerState.progress_data.length()),
            columns="3",
            gap="4",
            margin_bottom="6",
        ),
        rx.heading("Timeline", size="3", margin_bottom="3"),
        rx.cond(
            CareerState.is_loading,
            rx.spinner(size="3"),
            _timeline(),
        ),
        rx.cond(
            CareerState.error != "",
            rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            rx.fragment(),
        ),
        on_mount=CareerState.load_progress,
    )
