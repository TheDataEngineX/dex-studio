"""System metrics page — Prometheus metrics placeholder.

Route: ``/system/metrics``
"""

from __future__ import annotations

import logging

from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/system/metrics")
async def system_metrics_page() -> None:
    """Render the system metrics placeholder page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/metrics")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Metrics")
            with ui.column().classes("p-6 gap-4 w-full"):
                ui.label("Prometheus Metrics").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                with (
                    ui.card().classes("dex-card").style("padding: 16px;"),
                    ui.row().classes("items-start gap-3"),
                ):
                    ui.icon("info", size="sm").style(f"color: {COLORS['accent_light']}")
                    with ui.column().classes("gap-1"):
                        ui.label(
                            "Connect to the /metrics endpoint for Prometheus-format metrics."
                        ).classes("text-sm").style(f"color: {COLORS['text_primary']}")
                        if client is not None:
                            metrics_url = f"{client.config.api_url}/metrics"
                            ui.label(metrics_url).classes("text-xs font-mono").style(
                                f"color: {COLORS['accent_light']}"
                            )
                        ui.label(
                            "Use a Prometheus scrape config or a Grafana data source "
                            "pointed at the /metrics endpoint to visualise these metrics."
                        ).classes("text-xs").style(f"color: {COLORS['text_muted']}")

                empty_state(
                    "Metrics visualisation coming soon",
                    icon="bar_chart",
                )
