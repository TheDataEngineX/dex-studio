from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import metric_card, page_shell, skeleton_table
from dex_studio.state.data import PipelineState, QualityState, SourceState


def data_dashboard() -> rx.Component:
    return page_shell(
        "Data Dashboard",
        rx.cond(
            PipelineState.error != "",
            rx.callout.root(rx.callout.text(PipelineState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.grid(
            metric_card(
                "git-branch-plus", "Pipelines", PipelineState.pipelines.length(), accent="indigo"
            ),  # type: ignore[attr-defined]
            metric_card("database", "Sources", SourceState.sources.length(), accent="indigo"),  # type: ignore[attr-defined]
            metric_card(
                "shield-check", "Quality Score", QualityState.quality_score, accent="indigo"
            ),
            columns="3",
            gap="4",
            margin_bottom="6",
        ),
        rx.heading("Pipelines", size="3", margin_bottom="2"),
        rx.cond(
            PipelineState.is_loading,
            skeleton_table(rows=5, cols=4),
            rx.cond(
                PipelineState.pipelines.length() == 0,  # type: ignore[attr-defined]
                rx.center(
                    rx.vstack(
                        rx.icon("inbox", size=40, color="var(--gray-7)"),
                        rx.text("No pipelines found", weight="medium", color="var(--gray-10)"),
                        rx.text(
                            "Connect a DEX API or create your first pipeline.",
                            size="2",
                            color="var(--gray-8)",
                        ),
                        align="center",
                        spacing="2",
                        padding_y="10",
                    ),
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Status"),
                            rx.table.column_header_cell("Last Run"),
                            rx.table.column_header_cell("Action"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            PipelineState.pipelines,
                            lambda p: rx.table.row(
                                rx.table.cell(p["name"]),
                                rx.table.cell(
                                    rx.badge(
                                        p["status"],
                                        color_scheme=rx.cond(
                                            p["status"] == "success",
                                            "green",
                                            rx.cond(p["status"] == "running", "yellow", "red"),
                                        ),
                                    )
                                ),
                                rx.table.cell(p["last_run"]),
                                rx.table.cell(
                                    rx.button(
                                        "Run",
                                        size="1",
                                        on_click=PipelineState.run_pipeline(p["name"]),
                                    )
                                ),
                            ),
                        )
                    ),
                    width="100%",
                ),
            ),
        ),
        on_mount=[
            PipelineState.load_pipelines,
            SourceState.load_sources,
            QualityState.load_quality,
        ],
    )
