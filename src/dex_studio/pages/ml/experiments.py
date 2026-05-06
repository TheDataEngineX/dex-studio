from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


def ml_experiments() -> rx.Component:
    return page_shell(
        "Experiments",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.heading("Experiments", size="3", margin_bottom="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Runs"),
                    rx.table.column_header_cell("Created"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    MLState.experiments,
                    lambda e: rx.table.row(
                        rx.table.cell(
                            rx.link(
                                e["name"],
                                on_click=MLState.select_experiment(e["name"]),
                                cursor="pointer",
                            )
                        ),
                        rx.table.cell(e["run_count"]),
                        rx.table.cell(e["created_at"]),
                    ),
                )
            ),
            width="100%",
        ),
        rx.cond(
            MLState.selected_experiment != "",
            rx.vstack(
                rx.heading(
                    "Runs — ",
                    MLState.selected_experiment,
                    size="3",
                    margin_top="6",
                    margin_bottom="2",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Run ID"),
                            rx.table.column_header_cell("Status"),
                            rx.table.column_header_cell("Metric"),
                            rx.table.column_header_cell("Started"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            MLState.runs,
                            lambda r: rx.table.row(
                                rx.table.cell(r["run_id"]),
                                rx.table.cell(
                                    rx.badge(
                                        r["status"],
                                        color_scheme=rx.cond(
                                            r["status"] == "finished",
                                            "green",
                                            rx.cond(
                                                r["status"] == "running",
                                                "yellow",
                                                "gray",
                                            ),
                                        ),
                                    )
                                ),
                                rx.table.cell(r["primary_metric"]),
                                rx.table.cell(r["started_at"]),
                            ),
                        )
                    ),
                    width="100%",
                ),
                width="100%",
            ),
            rx.fragment(),
        ),
        on_mount=MLState.load_experiments,
    )
