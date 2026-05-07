from __future__ import annotations

from collections.abc import AsyncGenerator

import reflex as rx

from dex_studio.components.layout import page_shell


class HitlState(rx.State):
    queue: list[dict] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def load_queue(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        self.queue = []
        self.is_loading = False

    @rx.event
    async def approve(self, item_id: str) -> AsyncGenerator[None]:
        yield

    @rx.event
    async def reject(self, item_id: str) -> AsyncGenerator[None]:
        yield


def _queue_row(item: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(item["id"]),
        rx.table.cell(item["agent"]),
        rx.table.cell(item["action"]),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "Approve",
                    on_click=HitlState.approve(item["id"]),
                    color_scheme="green",
                    size="1",
                ),
                rx.button(
                    "Reject",
                    on_click=HitlState.reject(item["id"]),
                    color_scheme="red",
                    size="1",
                ),
                spacing="2",
            )
        ),
    )


def ai_hitl() -> rx.Component:
    return page_shell(
        "Human-in-the-Loop",
        rx.heading("Human-in-the-Loop Queue", size="5", margin_bottom="4"),
        rx.cond(HitlState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            HitlState.queue.length() == 0,
            rx.callout.root(
                rx.callout.text("No pending approvals. HITL queue is empty."),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("ID"),
                        rx.table.column_header_cell("Agent"),
                        rx.table.column_header_cell("Action"),
                        rx.table.column_header_cell("Decision"),
                    )
                ),
                rx.table.body(rx.foreach(HitlState.queue, _queue_row)),
            ),
        ),
        on_mount=HitlState.load_queue,
    )
