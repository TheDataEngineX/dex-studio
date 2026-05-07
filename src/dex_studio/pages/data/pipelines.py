from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell, skeleton_table
from dex_studio.state.data import PipelineState


def _status_badge(status: rx.Var) -> rx.Component:  # type: ignore[type-arg]
    return rx.cond(
        status == "success",
        rx.el.span(status, class_name="badge bg-success"),
        rx.cond(
            status == "running",
            rx.el.span(status, class_name="badge bg-warning text-dark"),
            rx.cond(
                status == "failed",
                rx.el.span(status, class_name="badge bg-danger"),
                rx.el.span(status, class_name="badge bg-secondary"),
            ),
        ),
    )


def _pipeline_row(p: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.el.tr(
        rx.el.td(
            rx.hstack(
                rx.box(
                    rx.icon("git-branch", size=14, color="var(--blue-9)"),
                    padding="6px",
                    background="var(--blue-2)",
                    border_radius="var(--radius-2)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
                rx.el.button(
                    p["name"],  # type: ignore[index]
                    class_name="btn btn-link p-0 text-start fw-medium text-decoration-none",
                    on_click=PipelineState.select_pipeline(p["name"]),  # type: ignore[index]
                    style={"font-size": "0.875rem"},
                ),
                spacing="2",
                align="center",
            ),
            class_name="align-middle",
        ),
        rx.el.td(_status_badge(p["status"]), class_name="align-middle"),  # type: ignore[index]
        rx.el.td(
            rx.text(p["last_run"], size="2", color="var(--gray-10)"),  # type: ignore[index]
            class_name="align-middle",
        ),
        rx.el.td(
            rx.text(p["duration_ms"].to(int).to_string() + " ms", size="2", color="var(--gray-10)"),  # type: ignore[index,attr-defined]
            class_name="align-middle",
        ),
        rx.el.td(
            rx.cond(
                PipelineState.pipeline_running == p["name"],  # type: ignore[index]
                rx.el.button(
                    rx.el.span(class_name="spinner-border spinner-border-sm me-1"),
                    "Running…",
                    class_name="btn btn-sm btn-outline-primary",
                    disabled=True,
                ),
                rx.el.button(
                    rx.icon("play", size=12),
                    " Run",
                    class_name="btn btn-sm btn-primary",
                    on_click=PipelineState.run_pipeline(p["name"]),  # type: ignore[index]
                ),
            ),
            class_name="align-middle",
        ),
    )


def _step_row(s: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.el.tr(
        rx.el.td(rx.badge(s["type"], color_scheme="blue"), class_name="align-middle"),  # type: ignore[index]
        rx.el.td(
            rx.text(
                rx.cond(
                    s["sql"] != "",  # type: ignore[index]
                    s["sql"],  # type: ignore[index]
                    rx.cond(s["condition"] != "", s["condition"], s["expression"]),  # type: ignore[index]
                ),
                size="1",
                color="var(--gray-10)",
            ),
            class_name="align-middle",
        ),
    )


def _history_row(r: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.el.tr(
        rx.el.td(
            rx.text(r["timestamp"], size="1", color="var(--gray-9)"), class_name="align-middle"
        ),  # type: ignore[index]
        rx.el.td(
            rx.cond(
                r["success"],  # type: ignore[index]
                rx.el.span("success", class_name="badge bg-success"),
                rx.el.span("failed", class_name="badge bg-danger"),
            ),
            class_name="align-middle",
        ),
        rx.el.td(rx.text(r["rows_input"].to(int).to_string(), size="1"), class_name="align-middle"),  # type: ignore[index,attr-defined]
        rx.el.td(
            rx.text(r["rows_output"].to(int).to_string(), size="1"), class_name="align-middle"
        ),  # type: ignore[index,attr-defined]
        rx.el.td(
            rx.text(r["duration_ms"].to(int).to_string() + " ms", size="1"),
            class_name="align-middle",
        ),  # type: ignore[index,attr-defined]
        rx.el.td(
            rx.text(r["error"], size="1", color="var(--red-9)"),  # type: ignore[index]
            class_name="align-middle",
        ),
    )


def _pipeline_detail_panel() -> rx.Component:
    return rx.cond(
        PipelineState.selected_pipeline != "",
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.hstack(
                        rx.icon("git-branch", size=16, color="var(--blue-9)"),
                        rx.text(PipelineState.selected_pipeline, weight="bold", size="3"),
                        rx.el.button(
                            "✕ Close",
                            class_name="btn btn-sm btn-outline-secondary ms-auto",
                            on_click=PipelineState.select_pipeline(""),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    class_name="card-header py-2",
                ),
                rx.el.div(
                    # Metadata row
                    rx.el.div(
                        rx.el.div(
                            rx.text("Source", size="1", color="var(--gray-9)"),
                            rx.badge(
                                PipelineState.pipeline_detail["source"], color_scheme="indigo"
                            ),  # type: ignore[index]
                            class_name="col-auto",
                        ),
                        rx.el.div(
                            rx.text("Destination", size="1", color="var(--gray-9)"),
                            rx.cond(
                                PipelineState.pipeline_detail["destination"] != "",  # type: ignore[index]
                                rx.text(PipelineState.pipeline_detail["destination"], size="2"),  # type: ignore[index]
                                rx.text("—", size="2", color="var(--gray-8)"),
                            ),
                            class_name="col-auto",
                        ),
                        rx.el.div(
                            rx.text("Schedule", size="1", color="var(--gray-9)"),
                            rx.cond(
                                PipelineState.pipeline_detail["schedule"] != "",  # type: ignore[index]
                                rx.badge(
                                    PipelineState.pipeline_detail["schedule"], color_scheme="green"
                                ),  # type: ignore[index]
                                rx.text("—", size="2", color="var(--gray-8)"),
                            ),
                            class_name="col-auto",
                        ),
                        rx.el.div(
                            rx.text("Depends on", size="1", color="var(--gray-9)"),
                            rx.cond(
                                PipelineState.pipeline_detail["depends_on"] != "",  # type: ignore[index]
                                rx.text(PipelineState.pipeline_detail["depends_on"], size="2"),  # type: ignore[index]
                                rx.text("—", size="2", color="var(--gray-8)"),
                            ),
                            class_name="col-auto",
                        ),
                        class_name="row g-4 mb-4",
                    ),
                    # Transforms table
                    rx.cond(
                        PipelineState.pipeline_steps.length() > 0,  # type: ignore[attr-defined]
                        rx.vstack(
                            rx.text("Transforms", weight="medium", size="2"),
                            rx.el.div(
                                rx.el.table(
                                    rx.el.thead(
                                        rx.el.tr(
                                            rx.el.th("Type", scope="col"),
                                            rx.el.th("Expression / SQL / Condition", scope="col"),
                                        ),
                                    ),
                                    rx.el.tbody(
                                        rx.foreach(PipelineState.pipeline_steps, _step_row),
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
                    # Run history
                    rx.vstack(
                        rx.text("Run History", weight="medium", size="2"),
                        rx.cond(
                            PipelineState.pipeline_history.length() == 0,  # type: ignore[attr-defined]
                            rx.text("No runs recorded yet.", size="2", color="var(--gray-8)"),
                            rx.el.div(
                                rx.el.table(
                                    rx.el.thead(
                                        rx.el.tr(
                                            rx.el.th("Timestamp", scope="col"),
                                            rx.el.th("Status", scope="col"),
                                            rx.el.th("Rows In", scope="col"),
                                            rx.el.th("Rows Out", scope="col"),
                                            rx.el.th("Duration", scope="col"),
                                            rx.el.th("Error", scope="col"),
                                        ),
                                    ),
                                    rx.el.tbody(
                                        rx.foreach(PipelineState.pipeline_history, _history_row),
                                    ),
                                    class_name="table table-sm table-hover mb-0",
                                ),
                                class_name="card border-0",
                                style={"overflow": "hidden"},
                            ),
                        ),
                        spacing="2",
                        align_items="flex-start",
                        width="100%",
                    ),
                    class_name="card-body",
                ),
                class_name="card shadow-sm border-0 mt-4",
            ),
        ),
        rx.fragment(),
    )


def _result_panel() -> rx.Component:
    return rx.cond(
        PipelineState.pipeline_last_result.length() > 0,  # type: ignore[attr-defined]
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.hstack(
                        rx.icon("circle-check", size=16, color="var(--green-9)"),
                        rx.text("Last Run Result", weight="bold", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    class_name="card-header py-2",
                    style={"background": "var(--green-2)", "border-color": "var(--green-5)"},
                ),
                rx.el.div(
                    rx.el.div(
                        rx.el.div(
                            rx.text("Status", size="1", color="var(--gray-9)"),
                            rx.el.span(
                                PipelineState.pipeline_last_result["status"],  # type: ignore[index]
                                class_name="badge bg-success ms-2",
                            ),
                            class_name="col-auto d-flex align-items-center",
                        ),
                        rx.el.div(
                            rx.text("Rows In", size="1", color="var(--gray-9)"),
                            rx.text(
                                PipelineState.pipeline_last_result["rows_input"]
                                .to(int)
                                .to_string(),  # type: ignore[index,attr-defined]
                                weight="bold",
                                size="2",
                            ),
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Rows Out", size="1", color="var(--gray-9)"),
                            rx.text(
                                PipelineState.pipeline_last_result["rows_output"]
                                .to(int)
                                .to_string(),  # type: ignore[index,attr-defined]
                                weight="bold",
                                size="2",
                            ),
                            class_name="col-auto text-center",
                        ),
                        rx.el.div(
                            rx.text("Duration", size="1", color="var(--gray-9)"),
                            rx.text(
                                PipelineState.pipeline_last_result["duration_ms"]
                                .to(int)
                                .to_string()
                                + " ms",  # type: ignore[index,attr-defined]
                                weight="bold",
                                size="2",
                            ),
                            class_name="col-auto text-center",
                        ),
                        class_name="row g-4 align-items-center",
                    ),
                    class_name="card-body py-3",
                ),
                class_name="card border-success",
            ),
            class_name="mb-4",
        ),
        rx.fragment(),
    )


def _job_status_banner() -> rx.Component:
    return rx.cond(
        PipelineState.pipeline_running != "",
        rx.el.div(
            rx.hstack(
                rx.el.span(class_name="spinner-border spinner-border-sm text-primary"),
                rx.text(
                    "Running: ",
                    rx.el.strong(PipelineState.pipeline_running),
                    " — ",
                    PipelineState.pipeline_job_status,
                    size="2",
                ),
                spacing="2",
                align="center",
            ),
            class_name="alert alert-info d-flex align-items-center gap-2 py-2 mb-4",
        ),
        rx.fragment(),
    )


def data_pipelines() -> rx.Component:
    return page_shell(
        "Pipelines",
        rx.cond(
            PipelineState.error != "",
            rx.callout.root(
                rx.callout.text(PipelineState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        _job_status_banner(),
        _result_panel(),
        rx.cond(
            PipelineState.is_loading,
            skeleton_table(rows=5, cols=5),
            rx.cond(
                PipelineState.pipelines.length() == 0,  # type: ignore[attr-defined]
                rx.center(
                    rx.vstack(
                        rx.icon("inbox", size=40, color="var(--gray-7)"),
                        rx.text("No pipelines yet", weight="medium", color="var(--gray-10)"),
                        rx.text(
                            "Create a pipeline in your dex.yaml to get started.",
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
                                rx.el.th("Pipeline", scope="col"),
                                rx.el.th("Status", scope="col"),
                                rx.el.th("Last Run", scope="col"),
                                rx.el.th("Duration", scope="col"),
                                rx.el.th("", scope="col"),
                            ),
                        ),
                        rx.el.tbody(
                            rx.foreach(PipelineState.pipelines, _pipeline_row),
                        ),
                        class_name="table table-hover align-middle mb-0",
                    ),
                    class_name="card shadow-sm border-0",
                    style={"overflow": "hidden"},
                ),
            ),
        ),
        _pipeline_detail_panel(),
        on_mount=PipelineState.load_pipelines,
    )
