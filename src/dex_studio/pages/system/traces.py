"""System traces page — OpenTelemetry trace viewer (coming soon).

Route: ``/system/traces``
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


@ui.page("/system/traces")
async def system_traces_page() -> None:
    """Render the OpenTelemetry trace viewer placeholder page."""
    apply_global_styles()
    _client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/traces")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Traces")
            with ui.column().classes("p-6 gap-4 w-full"):
                ui.label("Distributed Traces").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                with (
                    ui.card().classes("dex-card").style("padding: 16px;"),
                    ui.row().classes("items-start gap-3"),
                ):
                    ui.icon("info", size="sm").style(f"color: {COLORS['accent_light']}")
                    with ui.column().classes("gap-1"):
                        ui.label("OpenTelemetry trace visualisation is coming soon.").classes(
                            "text-sm"
                        ).style(f"color: {COLORS['text_primary']}")
                        ui.label(
                            "Traces are collected via the /api/v1/system/traces endpoint. "
                            "Connect an OpenTelemetry-compatible backend (Jaeger, Tempo, "
                            "Zipkin) for full distributed tracing support."
                        ).classes("text-xs").style(f"color: {COLORS['text_muted']}")

                empty_state(
                    "Trace viewer coming soon",
                    icon="timeline",
                )
