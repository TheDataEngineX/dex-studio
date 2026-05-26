from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _contact_row(c: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(c["name"], weight="bold")),
        rx.table.cell(c.get("company", "—")),
        rx.table.cell(c.get("role", "—")),
        rx.table.cell(c.get("last_contact", "—")),
    )


def network_page() -> rx.Component:
    return page_shell(
        "Network",
        rx.cond(CareerState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            CareerState.contacts.length() == 0,
            rx.callout.root(
                rx.callout.text("No contacts yet. Add people to grow your network."),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Company"),
                        rx.table.column_header_cell("Role"),
                        rx.table.column_header_cell("Last Contact"),
                    )
                ),
                rx.table.body(rx.foreach(CareerState.contacts, _contact_row)),
            ),
        ),
        on_mount=CareerState.load_contacts,
    )
