from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _contacts_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Name"),
                rx.table.column_header_cell("Company"),
                rx.table.column_header_cell("Role"),
                rx.table.column_header_cell("Email"),
                rx.table.column_header_cell("Last Contact"),
            )
        ),
        rx.table.body(
            rx.foreach(
                CareerState.contacts,
                lambda c: rx.table.row(
                    rx.table.cell(c.get("name", "")),
                    rx.table.cell(c.get("company", "")),
                    rx.table.cell(c.get("role", "")),
                    rx.table.cell(c.get("email", "")),
                    rx.table.cell(c.get("last_contact", "—")),
                ),
            )
        ),
    )


def networking_page() -> rx.Component:
    return page_shell(
        "Networking",
        rx.hstack(
            rx.heading("Networking", size="5"),
            rx.spacer(),
            rx.button("+ Add Contact", variant="solid", color_scheme="blue"),
            margin_bottom="4",
        ),
        rx.input(
            placeholder="Search contacts...",
            on_change=CareerState.set_search_query,
            margin_bottom="4",
            width="300px",
        ),
        rx.cond(
            CareerState.is_loading,
            rx.spinner(size="3"),
            _contacts_table(),
        ),
        rx.cond(
            CareerState.error != "",
            rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            rx.fragment(),
        ),
        on_mount=CareerState.load_contacts,
    )
