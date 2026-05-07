from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import SQLState


def data_sql_console() -> rx.Component:
    return page_shell(
        "SQL Console",
        rx.vstack(
            rx.text_area(
                value=SQLState.sql_query,
                on_change=SQLState.set_sql_query,
                placeholder="SELECT 1",
                rows="6",
                font_family="monospace",
                width="100%",
            ),
            rx.hstack(
                rx.button(
                    "Execute",
                    on_click=SQLState.execute_sql,
                    loading=SQLState.is_loading,
                ),
                rx.cond(
                    SQLState.sql_exec_ms > 0,
                    rx.text(
                        SQLState.sql_results.length(),  # type: ignore[attr-defined]
                        " rows · ",
                        SQLState.sql_exec_ms,
                        "ms",
                        size="1",
                        color="gray",
                    ),
                    rx.fragment(),
                ),
                spacing="3",
            ),
            rx.cond(
                SQLState.sql_error != "",
                rx.callout.root(rx.callout.text(SQLState.sql_error), color="red"),
                rx.fragment(),
            ),
            rx.cond(
                SQLState.sql_results.length() > 0,  # type: ignore[attr-defined]
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.foreach(
                                SQLState.sql_columns,
                                lambda c: rx.table.column_header_cell(c),
                            )
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            SQLState.sql_results,
                            lambda row: rx.table.row(
                                rx.foreach(
                                    SQLState.sql_columns,
                                    lambda c: rx.table.cell(row[c]),
                                )
                            ),
                        )
                    ),
                    width="100%",
                ),
                rx.fragment(),
            ),
            width="100%",
            spacing="3",
        ),
    )
