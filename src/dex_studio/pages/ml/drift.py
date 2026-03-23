"""ML drift monitor page — PSI-based drift detection.

Route: ``/ml/drift``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.status_badge import status_badge
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_PSI_COLUMNS: list[dict[str, Any]] = [
    {"name": "feature", "label": "Feature", "field": "feature", "align": "left"},
    {"name": "psi", "label": "PSI Score", "field": "psi", "align": "right"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
]

# PSI thresholds: < 0.1 stable, 0.1–0.2 moderate drift, > 0.2 significant drift
_PSI_STABLE = 0.1
_PSI_MODERATE = 0.2


def _psi_status(psi: float) -> str:
    """Return a drift status label from a PSI score."""
    if psi < _PSI_STABLE:
        return "stable"
    if psi < _PSI_MODERATE:
        return "degraded"
    return "failed"


def _render_feature_scores(feature_scores: list[dict[str, Any]]) -> None:
    """Render per-feature PSI breakdown table."""
    ui.label("Feature Drift Breakdown").classes("section-title mt-4")
    rows: list[dict[str, Any]] = []
    for fs in feature_scores:
        psi_val: Any = fs.get("psi", fs.get("score"))
        psi_float = float(psi_val) if psi_val is not None else 0.0
        rows.append(
            {
                "feature": fs.get("feature", fs.get("name", "—")),
                "psi": (f"{psi_float:.4f}" if isinstance(psi_val, float) else str(psi_val)),
                "status": _psi_status(psi_float),
            }
        )
    data_table(_PSI_COLUMNS, rows, title="Feature PSI Scores")


def _render_drift_raw(result: dict[str, Any]) -> None:
    """Render raw drift result as key-value pairs when no feature breakdown is available."""
    ui.label("Drift Details").classes("section-title mt-4")
    with ui.card().classes("dex-card w-full"), ui.grid(columns=2).classes("gap-x-6 gap-y-2 p-4"):
        for key, val in result.items():
            ui.label(key).classes("text-xs font-mono").style(f"color: {COLORS['text_muted']}")
            ui.label(str(val)).classes("text-sm").style(f"color: {COLORS['text_primary']}")


def _render_drift_summary(pipeline_name: str, result: dict[str, Any]) -> None:
    """Render drift summary row with overall status and score."""
    overall_status: str = result.get("status", "unknown")
    drift_score: Any = result.get("drift_score", result.get("psi"))

    ui.label("Summary").classes("section-title")
    with ui.row().classes("items-center gap-3"):
        ui.label(f"Pipeline: {pipeline_name}").classes("text-sm font-semibold").style(
            f"color: {COLORS['text_primary']}"
        )
        status_badge(overall_status)
        if drift_score is not None:
            formatted = f"{drift_score:.4f}" if isinstance(drift_score, float) else str(drift_score)
            ui.label(f"Overall PSI: {formatted}").classes("text-xs").style(
                f"color: {COLORS['text_muted']}"
            )

    feature_scores: list[dict[str, Any]] = result.get("feature_scores", result.get("features", []))
    if feature_scores:
        _render_feature_scores(feature_scores)
    else:
        _render_drift_raw(result)


@ui.page("/ml/drift")
async def ml_drift_page() -> None:
    """Render the ML drift monitor page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/drift")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Drift Monitor")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Drift Monitor").classes("section-title")
                ui.label("Check PSI-based feature drift for a data pipeline.").classes(
                    "text-xs"
                ).style(f"color: {COLORS['text_muted']}")

                with ui.row().classes("items-end gap-3 mt-2"):
                    pipeline_input = (
                        ui.input(
                            label="Pipeline Name",
                            placeholder="e.g. customer_churn",
                        )
                        .classes("w-64")
                        .props("outlined dark")
                    )

                drift_container = ui.column().classes("w-full mt-4")

                async def check_drift() -> None:
                    pipeline_name = pipeline_input.value.strip()
                    if not pipeline_name:
                        return
                    drift_container.clear()
                    with drift_container:
                        try:
                            result = await client.check_drift(pipeline_name)
                        except DexAPIError as exc:
                            ui.label(f"Error: {exc}").style(f"color: {COLORS['error']}")
                            return
                        _render_drift_summary(pipeline_name, result)

                ui.button(
                    "Check Drift",
                    icon="trending_up",
                    on_click=check_drift,
                ).props("color=indigo")
