from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx

from dex_studio.components.layout import page_shell


class IncidentState(rx.State):
    incidents: list[dict[str, Any]] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def load_incidents(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        self.incidents = []
        self.is_loading = False


def _incident_row(inc: dict[str, Any]) -> rx.Component:
    return rx.table.row(
        rx.table.cell(inc["id"]),
        rx.table.cell(inc["title"]),
        rx.table.cell(
            rx.badge(
                inc["severity"],
                color_scheme=rx.cond(
                    inc["severity"] == "critical",
                    "red",
                    rx.cond(inc["severity"] == "warning", "yellow", "gray"),
                ),
            )
        ),
        rx.table.cell(
            rx.badge(
                inc["status"],
                color_scheme=rx.cond(inc["status"] == "open", "red", "green"),
            )
        ),
        rx.table.cell(inc["ts"]),
    )


def system_incidents() -> rx.Component:
    return page_shell(
        "Incidents",
        rx.cond(IncidentState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            IncidentState.incidents.length() == 0,
            rx.callout.root(
                rx.callout.text("No incidents. System is operating normally."),
                color_scheme="green",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("ID"),
                        rx.table.column_header_cell("Title"),
                        rx.table.column_header_cell("Severity"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Timestamp"),
                    )
                ),
                rx.table.body(rx.foreach(IncidentState.incidents, _incident_row)),
            ),
        ),
        on_mount=IncidentState.load_incidents,
    )
