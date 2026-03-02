"""Health page — detailed health and readiness view.

Route: ``/health``

Drives DEX engine endpoints:
    GET /health  → liveness probe
    GET /ready   → readiness probe (component-level)
    GET /startup → startup status
"""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import page_layout, status_card
from dex_studio.theme import COLORS


def _health_columns() -> list[dict[str, str]]:
    """Return table column definitions for component health."""
    return [
        {"name": "name", "label": "Component", "field": "name", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
        {"name": "message", "label": "Message", "field": "message", "align": "left"},
        {
            "name": "duration_ms",
            "label": "Latency (ms)",
            "field": "duration_ms",
            "align": "right",
        },
    ]


@ui.page("/health")
async def health_page() -> None:
    """Render the health dashboard."""
    with page_layout("Health & Readiness", active_route="/health") as _content:
        client: DexClient | None = app.storage.general.get("client")
        if client is None:
            ui.label("No connection configured.").style(f"color: {COLORS['error']}")
            return

        # Container for refreshable content
        health_container = ui.column().classes("w-full gap-4")

        async def refresh_health() -> None:
            health_container.clear()
            with health_container:
                # -- Liveness --
                try:
                    health = await client.health()
                    status_card(
                        "Liveness Probe",
                        health.get("status", "unknown"),
                        subtitle="GET /health",
                        icon="favorite",
                    )
                except DexAPIError as exc:
                    status_card("Liveness Probe", "error", subtitle=str(exc), icon="favorite")

                # -- Startup --
                try:
                    startup = await client.startup()
                    status_card(
                        "Startup Probe",
                        startup.get("status", "unknown"),
                        subtitle="GET /startup",
                        icon="rocket_launch",
                    )
                except DexAPIError as exc:
                    status_card("Startup Probe", "error", subtitle=str(exc), icon="rocket_launch")

                # -- Readiness (component breakdown) --
                try:
                    ready = await client.readiness()
                    overall = ready.get("status", "unknown")
                    status_card(
                        "Readiness Probe",
                        overall,
                        subtitle="GET /ready",
                        icon="check_circle",
                    )

                    components: list[dict[str, Any]] = ready.get("components", [])
                    if components:
                        ui.label("Component Health").classes("section-title mt-4")
                        with ui.card().classes("dex-card w-full"):
                            columns = _health_columns()

                            rows = [
                                {
                                    "name": c.get("name", "—"),
                                    "status": c.get("status", "unknown"),
                                    "message": c.get("message", "—"),
                                    "duration_ms": c.get("duration_ms", "—"),
                                }
                                for c in components
                            ]
                            ui.table(columns=columns, rows=rows).classes("w-full").style(
                                f"color: {COLORS['text_primary']}; "
                                f"background-color: {COLORS['bg_card']}"
                            )
                except DexAPIError:
                    status_card(
                        "Readiness Probe",
                        "unhealthy",
                        subtitle="Dependencies unhealthy or unreachable",
                        icon="check_circle",
                    )

        await refresh_health()

        # Refresh button
        ui.button(
            "Refresh",
            icon="refresh",
            on_click=refresh_health,
        ).classes("mt-4").props("flat color=indigo")
