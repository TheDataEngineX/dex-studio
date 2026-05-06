from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import SourceState


def _schema_row(col: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.el.tr(
        rx.el.td(rx.text(col["column_name"], size="1", weight="medium"), class_name="align-middle"),  # type: ignore[index]
        rx.el.td(rx.badge(col["column_type"], color_scheme="indigo"), class_name="align-middle"),  # type: ignore[index]
        rx.el.td(
            rx.text(col["nullable"], size="1", color="var(--gray-9)"), class_name="align-middle"
        ),  # type: ignore[index]
    )


def _sample_row(row: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.el.tr(
        rx.foreach(
            SourceState.source_sample_cols,
            lambda col: rx.el.td(row[col], class_name="align-middle"),
        ),  # type: ignore[index]
    )


def _source_detail_panel() -> rx.Component:
    return rx.cond(
        SourceState.selected_source != "",
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.hstack(
                        rx.icon("database", size=16, color="var(--indigo-9)"),
                        rx.text(SourceState.selected_source, weight="bold", size="3"),
                        rx.el.button(
                            "✕ Close",
                            class_name="btn btn-sm btn-outline-secondary ms-auto",
                            on_click=SourceState.select_source(""),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    class_name="card-header py-2",
                ),
                rx.el.div(
                    # Stats row
                    rx.el.div(
                        rx.el.div(
                            rx.text("Rows", size="1", color="var(--gray-9)"),
                            rx.text(
                                SourceState.source_detail["row_count"], weight="bold", size="3"
                            ),  # type: ignore[index]
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Columns", size="1", color="var(--gray-9)"),
                            rx.text(
                                SourceState.source_detail["column_count"], weight="bold", size="3"
                            ),  # type: ignore[index]
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Size", size="1", color="var(--gray-9)"),
                            rx.text(
                                SourceState.source_detail["size_label"], weight="bold", size="3"
                            ),  # type: ignore[index]
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Type", size="1", color="var(--gray-9)"),
                            rx.badge(
                                SourceState.source_detail["connector_type"], color_scheme="blue"
                            ),  # type: ignore[index]
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Path", size="1", color="var(--gray-9)"),
                            rx.text(
                                SourceState.source_detail["path"], size="1", color="var(--gray-10)"
                            ),  # type: ignore[index]
                            class_name="col-12",
                        ),
                        class_name="row g-4 mb-4",
                    ),
                    # Schema table
                    rx.cond(
                        SourceState.source_schema_cols.length() > 0,  # type: ignore[attr-defined]
                        rx.vstack(
                            rx.text("Schema", weight="medium", size="2"),
                            rx.el.div(
                                rx.el.table(
                                    rx.el.thead(
                                        rx.el.tr(
                                            rx.el.th("Column", scope="col"),
                                            rx.el.th("Type", scope="col"),
                                            rx.el.th("Nullable", scope="col"),
                                        ),
                                    ),
                                    rx.el.tbody(
                                        rx.foreach(SourceState.source_schema_cols, _schema_row),
                                    ),
                                    class_name="table table-sm mb-0",
                                ),
                                class_name="card border-0 bg-light mb-3",
                                style={"overflow": "hidden"},
                            ),
                            spacing="2",
                            align_items="flex-start",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    # Sample data
                    rx.cond(
                        SourceState.source_sample_rows.length() > 0,  # type: ignore[attr-defined]
                        rx.vstack(
                            rx.text("Sample Data (10 rows)", weight="medium", size="2"),
                            rx.el.div(
                                rx.el.div(
                                    rx.el.table(
                                        rx.el.thead(
                                            rx.el.tr(
                                                rx.foreach(
                                                    SourceState.source_sample_cols,
                                                    lambda c: rx.el.th(c, scope="col"),
                                                ),
                                            ),
                                        ),
                                        rx.el.tbody(
                                            rx.foreach(SourceState.source_sample_rows, _sample_row),
                                        ),
                                        class_name="table table-sm table-hover mb-0",
                                    ),
                                    style={"overflow-x": "auto"},
                                ),
                                class_name="card border-0",
                                style={"overflow": "hidden"},
                            ),
                            spacing="2",
                            align_items="flex-start",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    class_name="card-body",
                ),
                class_name="card shadow-sm border-0 mt-4",
            ),
        ),
        rx.fragment(),
    )


def data_sources() -> rx.Component:
    return page_shell(
        "Data Sources",
        rx.cond(
            SourceState.error != "",
            rx.callout.root(
                rx.callout.text(SourceState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.cond(SourceState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            SourceState.sources.length() == 0,  # type: ignore[attr-defined]
            rx.center(
                rx.vstack(
                    rx.icon("inbox", size=40, color="var(--gray-7)"),
                    rx.text("No sources configured", weight="medium", color="var(--gray-10)"),
                    rx.text(
                        "Add a source in your dex.yaml to get started.",
                        size="2",
                        color="var(--gray-8)",
                    ),
                    align="center",
                    spacing="2",
                    padding_y="10",
                ),
            ),
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Name", scope="col"),
                            rx.el.th("Type", scope="col"),
                            rx.el.th("Status", scope="col"),
                        ),
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            SourceState.sources,
                            lambda s: rx.el.tr(
                                rx.el.td(
                                    rx.el.button(
                                        s["name"],  # type: ignore[index]
                                        class_name="btn btn-link p-0 text-start fw-medium text-decoration-none",
                                        on_click=SourceState.select_source(s["name"]),  # type: ignore[index]
                                        style={"font-size": "0.875rem"},
                                    ),
                                    class_name="align-middle",
                                ),
                                rx.el.td(
                                    rx.badge(s["type"], color_scheme="indigo"),  # type: ignore[index]
                                    class_name="align-middle",
                                ),
                                rx.el.td(
                                    rx.badge(
                                        s["status"],  # type: ignore[index]
                                        color_scheme=rx.cond(
                                            s["status"] == "active", "green", "gray"
                                        ),  # type: ignore[index]
                                    ),
                                    class_name="align-middle",
                                ),
                            ),
                        ),
                    ),
                    class_name="table table-hover align-middle mb-0",
                ),
                class_name="card shadow-sm border-0",
                style={"overflow": "hidden"},
            ),
        ),
        _source_detail_panel(),
        on_mount=SourceState.load_sources,
    )
