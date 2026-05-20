from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import (
    empty_state,
    metric_card,
    page_shell,
    section_heading,
    skeleton_table,
    status_badge,
)
from dex_studio.state.data import PipelineState, QualityState, SourceState


def _pipeline_row(p: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.icon("git-branch-plus", size=13, color="var(--indigo-9)"),
                rx.text(p["name"], weight="medium", size="2"),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(status_badge(p["status"])),
        rx.table.cell(
            rx.text(p["last_run"], size="2", color="var(--gray-9)"),
        ),
        rx.table.cell(
            rx.button(
                rx.icon("play", size=12),
                "Run",
                size="1",
                variant="soft",
                color_scheme="indigo",
                on_click=PipelineState.run_pipeline(p["name"]),
            )
        ),
        _hover={"background": "var(--gray-2)"},
    )


def data_dashboard() -> rx.Component:
    return page_shell(
        "Data Dashboard",
        rx.cond(
            PipelineState.error != "",
            rx.callout.root(
                rx.callout.text(PipelineState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        # ── Metric cards ────────────────────────────────────────────────────
        rx.grid(
            metric_card(
                "git-branch-plus",
                "Pipelines",
                PipelineState.pipelines.length(),  # type: ignore[attr-defined]
                accent="indigo",
                subtitle="Total configured",
            ),
            metric_card(
                "database",
                "Sources",
                SourceState.sources.length(),  # type: ignore[attr-defined]
                accent="blue",
                subtitle="Connected data sources",
            ),
            metric_card(
                "shield-check",
                "Quality Score",
                QualityState.quality_score,  # type: ignore[arg-type]
                accent="green",
                subtitle="Aggregate gate pass rate",
            ),
            columns="3",
            gap="4",
            margin_bottom="6",
        ),
        # ── Pipelines section ────────────────────────────────────────────────
        section_heading(
            "Pipelines",
            subtitle="Recently configured data pipelines.",
            action=rx.link(
                rx.button(
                    "View all",
                    rx.icon("arrow-right", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="indigo",
                ),
                href="/data/pipelines",
                text_decoration="none",
            ),
        ),
        rx.cond(
            PipelineState.is_loading,
            skeleton_table(rows=5, cols=4),
            rx.cond(
                PipelineState.pipelines.length() == 0,  # type: ignore[attr-defined]
                empty_state(
                    "git-branch-plus",
                    "No pipelines configured",
                    "Connect a DEX project or add pipelines to your dex.yaml.",
                    action=rx.link(
                        rx.button(
                            "Open pipelines",
                            size="2",
                            color_scheme="indigo",
                            variant="soft",
                        ),
                        href="/data/pipelines",
                        text_decoration="none",
                    ),
                ),
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Name"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Last Run"),
                                rx.table.column_header_cell("Actions"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(PipelineState.pipelines, _pipeline_row),
                        ),
                        width="100%",
                        class_name="dex-table",
                    ),
                    background="var(--gray-2)",
                    border="1px solid var(--gray-4)",
                    border_radius="var(--radius-3)",
                    overflow="hidden",
                ),
            ),
        ),
        on_mount=[
            PipelineState.load_pipelines,
            SourceState.load_sources,
            QualityState.load_quality,
        ],
    )
