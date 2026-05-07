from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.system import SystemState

_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def _log_row(log: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(log["ts"]),
        rx.table.cell(
            rx.badge(
                log["level"],
                color_scheme=rx.cond(
                    log["level"] == "ERROR",
                    "red",
                    rx.cond(log["level"] == "WARNING", "yellow", "gray"),
                ),
            )
        ),
        rx.table.cell(log["msg"]),
    )


def _level_tab(level: str) -> rx.Component:
    return rx.button(
        level,
        on_click=SystemState.set_log_level(level),
        color_scheme=rx.cond(SystemState.log_level == level, "indigo", "gray"),
        variant=rx.cond(SystemState.log_level == level, "solid", "soft"),
        size="2",
    )


def system_logs() -> rx.Component:
    return page_shell(
        "Logs",
        rx.heading("System Logs", size="5", margin_bottom="4"),
        rx.hstack(
            *[_level_tab(lv) for lv in _LEVELS],
            spacing="2",
            margin_bottom="4",
        ),
        rx.cond(SystemState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            SystemState.error != "",
            rx.callout.root(
                rx.callout.text(SystemState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Timestamp"),
                    rx.table.column_header_cell("Level"),
                    rx.table.column_header_cell("Message"),
                )
            ),
            rx.table.body(rx.foreach(SystemState.logs, _log_row)),
        ),
        on_mount=SystemState.load_logs,
    )
