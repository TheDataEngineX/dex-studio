"""ML drift monitor page — PSI-based drift detection.

Route: ``/ml/drift``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from dex_studio.app import get_engine, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.components.status_badge import status_badge
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_PSI_COLUMNS: list[dict[str, Any]] = [
    {
        "name": "feature",
        "label": "Feature",
        "field": "feature",
        "align": "left",
    },
    {
        "name": "psi",
        "label": "PSI Score",
        "field": "psi",
        "align": "right",
    },
    {
        "name": "severity",
        "label": "Severity",
        "field": "severity",
        "align": "left",
    },
]


def _render_drift_results(reports: list[Any]) -> None:
    """Render per-feature drift report table."""
    if not reports:
        empty_state("No drift data available", icon="trending_flat")
        return

    rows: list[dict[str, Any]] = []
    for r in reports:
        rows.append(
            {
                "feature": r.feature_name,
                "psi": f"{r.psi:.6f}",
                "severity": r.severity,
            }
        )

    # Determine overall severity
    severities = [r.severity for r in reports]
    if "severe" in severities:
        overall = "severe"
    elif "moderate" in severities:
        overall = "moderate"
    else:
        overall = "none"

    ui.label("Summary").classes("section-title")
    with ui.row().classes("items-center gap-3"):
        status_badge(overall)
        ui.label(f"{len(reports)} feature(s) checked").classes("text-xs").style(
            f"color: {COLORS['text_muted']}"
        )

    ui.label("Feature Drift Breakdown").classes("section-title mt-4")
    data_table(_PSI_COLUMNS, rows, title="Feature PSI Scores")


@ui.page("/ml/drift")
async def ml_drift_page() -> None:
    """Render the ML drift monitor page."""
    apply_global_styles(get_theme())
    engine: DexEngine | None = get_engine()

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/drift")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Drift Monitor")
            with ui.column().classes("p-6 gap-4 w-full"):
                if engine is None:
                    ui.label("No engine configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Drift Monitor").classes("section-title")
                ui.label("Check PSI-based feature drift for a data pipeline.").classes(
                    "text-xs"
                ).style(f"color: {COLORS['text_muted']}")

                ui.label(
                    "Use the DriftDetector API to detect distribution"
                    " drift between reference and current datasets."
                ).classes("text-xs").style(f"color: {COLORS['text_dim']}")

                empty_state(
                    "Submit reference and current datasets via the "
                    "DriftDetector API to check for drift",
                    icon="trending_up",
                )
