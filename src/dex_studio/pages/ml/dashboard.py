from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import metric_card, page_shell
from dex_studio.state.ml import MLState


def ml_dashboard() -> rx.Component:
    return page_shell(
        "ML Dashboard",
        rx.cond(
            MLState.error != "",
            rx.callout.root(rx.callout.text(MLState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(MLState.is_loading, rx.spinner(), rx.fragment()),
        rx.grid(
            metric_card("box", "Models", MLState.models.length(), accent="violet"),  # type: ignore[attr-defined]
            metric_card(
                "flask-conical", "Experiments", MLState.experiments.length(), accent="violet"
            ),  # type: ignore[attr-defined]
            metric_card(
                "layers", "Feature Groups", MLState.feature_groups.length(), accent="violet"
            ),  # type: ignore[attr-defined]
            columns="3",
            gap="4",
            margin_bottom="6",
        ),
        rx.heading("Recent Models", size="3", margin_bottom="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Name"),
                    rx.table.column_header_cell("Version"),
                    rx.table.column_header_cell("Stage"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    MLState.models,
                    lambda m: rx.table.row(
                        rx.table.cell(m["name"]),
                        rx.table.cell(m["version"]),
                        rx.table.cell(
                            rx.badge(
                                m["stage"],
                                color_scheme=rx.cond(
                                    m["stage"] == "production",
                                    "green",
                                    rx.cond(m["stage"] == "staging", "yellow", "gray"),
                                ),
                            )
                        ),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=[MLState.load_models, MLState.load_experiments, MLState.load_features],
    )
