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
from dex_studio.components import status_badge
from dex_studio.components.page_layout import page_layout
from dex_studio.theme import COLORS

_ROW_CLASSES = "items-center gap-2"
_LABEL_CLASSES = "text-sm font-semibold"


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


def _probe_row(probe_name: str, status: str, subtitle: str | None = None) -> None:
    """Render a single probe row with label, status badge, and optional subtitle."""
    with ui.row().classes(_ROW_CLASSES):
        ui.label(probe_name).classes(_LABEL_CLASSES).style(f"color: {COLORS['text_primary']}")
        status_badge(status)
        if subtitle:
            ui.label(subtitle).classes("text-xs").style(f"color: {COLORS['text_muted']}")


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
                    _probe_row("Liveness Probe", health.get("status", "unknown"))
                except DexAPIError as exc:
                    _probe_row("Liveness Probe", "error", subtitle=str(exc))

                # -- Components (replaces readiness/startup probes) --
                try:
                    comp_resp = await client.components()
                    components: list[dict[str, Any]] = comp_resp.get("components", [])
                    _probe_row(
                        "Components",
                        "alive" if components else "unknown",
                    )

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
                    _probe_row("Components", "unhealthy", subtitle="Components unreachable")

        await refresh_health()

        # Refresh button
        ui.button(
            "Refresh",
            icon="refresh",
            on_click=refresh_health,
        ).classes("mt-4").props("flat color=indigo")
