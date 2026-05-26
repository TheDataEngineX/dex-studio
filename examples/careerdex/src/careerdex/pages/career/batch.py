from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _pending_count_badge() -> rx.Component:
    pending = len([j for j in CareerState.batch_jobs if j.get("status") == "pending"])
    return rx.text(f"{pending} pending", size="2", color="var(--gray-9)")


def _job_row(job: dict) -> rx.Component:
    status_color = rx.cond(
        job.get("status") == "applied",
        "green",
        rx.cond(
            job.get("status") == "failed",
            "red",
            rx.cond(job.get("status") == "applying", "blue", "gray"),
        ),
    )
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.checkbox(size="2"),
                rx.icon(
                    "globe" if "http" in str(job.get("url", "")) else "file",
                    size=14,
                    color="var(--gray-9)",
                ),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(job.get("company", "?"), weight="medium"),
        rx.table.cell(job.get("role", "")),
        rx.table.cell(
            rx.text(
                job.get("url", ""),
                size="1",
                color="var(--blue-10)",
                overflow="hidden",
                text_overflow="ellipsis",
                max_width="200px",
            ),
        ),
        rx.table.cell(
            rx.badge(job.get("status", "pending"), color_scheme=status_color, variant="soft"),
        ),
    )


def batch_page() -> rx.Component:
    return page_shell(
        "Batch Runner",
        rx.vstack(
            rx.hstack(
                rx.icon("layers", size=18, color="var(--blue-9)"),
                rx.heading("Batch Job Processing", size="5"),
                rx.spacer(),
                rx.cond(
                    CareerState.batch_jobs.length() > 0,
                    rx.hstack(
                        rx.button(
                            rx.icon("zap", size=14),
                            "Apply All",
                            color_scheme="green",
                            on_click=lambda: CareerState.apply_batch_jobs(),
                        ),
                        rx.button(
                            "Clear All",
                            color_scheme="red",
                            variant="outline",
                            on_click=lambda: CareerState.clear_batch_jobs(),
                        ),
                        spacing="2",
                    ),
                    rx.fragment(),
                ),
                align="center",
                width="100%",
            ),
            rx.text(
                "Add jobs to batch, then apply to all with one click.",
                size="2",
                color="var(--gray-9)",
                margin_bottom="4",
            ),
            rx.card(
                rx.vstack(
                    rx.text("Add Job to Batch", size="3", weight="bold"),
                    rx.hstack(
                        rx.input(
                            placeholder="Company",
                            on_change=CareerState.set_batch_company,
                            value=CareerState.batch_company_input,
                            width="200px",
                        ),
                        rx.input(
                            placeholder="Role / Position",
                            on_change=CareerState.set_batch_role,
                            value=CareerState.batch_role_input,
                            width="200px",
                        ),
                        rx.input(
                            placeholder="Job URL (optional)",
                            on_change=CareerState.set_batch_url,
                            value=CareerState.batch_url_input,
                            flex="1",
                        ),
                        rx.button(
                            rx.icon("plus", size=14),
                            "Add",
                            color_scheme="blue",
                            on_click=lambda: CareerState.add_batch_job(),
                        ),
                        spacing="2",
                    ),
                    spacing="3",
                ),
                padding="4",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.center(rx.spinner(), padding_y="6"),
            ),
            rx.cond(
                CareerState.error != "",
                rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            ),
            rx.cond(
                CareerState.batch_jobs.length() > 0,
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.heading(
                                f"Batch Jobs ({CareerState.batch_jobs.length()})",
                                size="4",
                            ),
                            rx.spacer(),
                            _pending_count_badge(),
                            align="center",
                        ),
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell(""),
                                    rx.table.column_header_cell("Company"),
                                    rx.table.column_header_cell("Role"),
                                    rx.table.column_header_cell("URL"),
                                    rx.table.column_header_cell("Status"),
                                )
                            ),
                            rx.table.body(rx.foreach(CareerState.batch_jobs, _job_row)),
                        ),
                        spacing="3",
                    ),
                    padding="4",
                ),
                rx.callout.root(
                    rx.hstack(
                        rx.icon("inbox", size=18),
                        rx.text("No jobs in batch. Add URLs above to start batch processing."),
                        spacing="2",
                    ),
                    color_scheme="gray",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
