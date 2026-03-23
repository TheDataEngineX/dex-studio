"""Data quality page — quality gates summary and per-pipeline results.

Route: ``/data/quality``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _pass_rate_parts(summary: dict[str, Any]) -> tuple[str, str]:
    """Return (display_str, color) for the overall pass rate."""
    raw = summary.get("overall_pass_rate", summary.get("pass_rate"))
    if isinstance(raw, (int, float)):
        color = COLORS["success"] if raw >= 0.8 else COLORS["warning"]
        return f"{raw:.0%}", color
    return "—", COLORS["text_muted"]


def _failures_color(failed: Any) -> str:
    """Return color for the failures metric."""
    return COLORS["error"] if isinstance(failed, int) and failed > 0 else COLORS["success"]


def _render_pipeline_row(entry: dict[str, Any]) -> None:
    """Render a single per-pipeline quality row card."""
    pipeline_name: str = entry.get("name", "—")
    p_pass_rate: Any = entry.get("pass_rate")
    p_pass_str = f"{p_pass_rate:.0%}" if isinstance(p_pass_rate, (int, float)) else "—"
    p_color = (
        COLORS["success"]
        if isinstance(p_pass_rate, (int, float)) and p_pass_rate >= 0.8
        else COLORS["warning"]
    )
    with ui.card().classes("dex-card w-full"):  # noqa: SIM117
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(pipeline_name).classes("text-sm font-semibold").style(
                f"color: {COLORS['text_primary']}"
            )
            ui.label(p_pass_str).style(f"font-weight: 700; color: {p_color};")


def _render_pipeline_breakdown(pipelines_quality: list[Any]) -> None:
    """Render the per-pipeline quality breakdown section."""
    ui.label("Per-Pipeline Quality").classes("section-title mt-4")
    with ui.column().classes("gap-2 w-full"):
        for entry in pipelines_quality:
            if isinstance(entry, dict):
                _render_pipeline_row(entry)


def _render_summary_metrics(summary: dict[str, Any]) -> None:
    """Render the three summary metric cards."""
    pass_rate_str, pass_rate_color = _pass_rate_parts(summary)
    total_checks = summary.get("total_checks", summary.get("total_evaluations", "—"))
    failed_checks = summary.get("failed_checks", "—")

    with ui.row().classes("gap-4 flex-wrap"):
        metric_card("Pass Rate", pass_rate_str, color=pass_rate_color)
        metric_card("Total Checks", total_checks)
        metric_card("Failures", failed_checks, color=_failures_color(failed_checks))


@ui.page("/data/quality")
async def data_quality_page() -> None:
    """Render the data quality gates page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="data")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("data", active_route="/data/quality")
        with ui.column().classes("flex-1"):
            breadcrumb("Data", "Quality Gates")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                try:
                    summary = await client.data_quality_summary()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch quality summary: %s", exc)
                    ui.label("Failed to load quality summary.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Summary").classes("section-title")
                _render_summary_metrics(summary)

                pipelines_quality: list[Any] = summary.get("pipelines", [])
                if isinstance(pipelines_quality, list) and pipelines_quality:
                    _render_pipeline_breakdown(pipelines_quality)
