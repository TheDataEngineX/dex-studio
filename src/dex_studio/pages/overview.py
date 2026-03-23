"""Overview page — main dashboard showing system health and key metrics.

Route: ``/``

Drives DEX engine endpoints:
    GET /            → API name + version
    GET /health      → liveness
    GET /startup     → startup status
    GET /api/v1/data/quality → quality summary
    GET /api/v1/system/config → system config
"""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import metric_card, status_badge
from dex_studio.components.page_layout import page_layout
from dex_studio.theme import COLORS


@ui.page("/")
async def overview_page() -> None:
    """Render the overview dashboard."""
    with page_layout("Overview", active_route="/") as _content:
        client: DexClient | None = app.storage.general.get("client")

        if client is None:
            ui.label("No connection configured.").style(f"color: {COLORS['error']}")
            return

        # -- Fetch all data concurrently --
        import asyncio

        results: dict[str, Any] = {}
        errors: list[str] = []

        async def _fetch(key: str, coro: Any) -> None:
            try:
                results[key] = await coro
            except DexAPIError as exc:
                errors.append(f"{key}: {exc}")
                results[key] = None

        await asyncio.gather(
            _fetch("root", client.root()),
            _fetch("health", client.health()),
            _fetch("components", client.components()),
            _fetch("quality", client.data_quality_summary()),
        )

        # -- Error banner --
        if errors:
            with ui.card().classes("dex-card w-full").style(f"border-color: {COLORS['warning']}"):
                ui.label("Some endpoints unreachable").classes("font-semibold text-sm").style(
                    f"color: {COLORS['warning']}"
                )
                for err in errors:
                    ui.label(f"• {err}").classes("text-xs").style(f"color: {COLORS['text_muted']}")

        # -- Row 1: Status cards --
        ui.label("System Status").classes("section-title")
        with ui.row().classes("gap-4 flex-wrap"):
            root = results.get("root") or {}
            api_version = root.get("version", "—")
            api_name = root.get("message", "DEX API")

            health = results.get("health") or {}
            health_status = health.get("status", "unknown")

            components_resp = results.get("components") or {}
            components_list: list[dict[str, Any]] = components_resp.get("components", [])
            components_status = "alive" if components_list else "unknown"

            with ui.card().classes("dex-card").style("padding: 12px; min-width: 160px;"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("api", size="sm").style(f"color: {COLORS['accent']}")
                    ui.label("API").classes("text-sm font-semibold").style(
                        f"color: {COLORS['text_primary']}"
                    )
                    status_badge(health_status)
                ui.label(f"{api_name} {api_version}").classes("text-xs").style(
                    f"color: {COLORS['text_muted']}"
                )
            with ui.card().classes("dex-card").style("padding: 12px; min-width: 160px;"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("extension", size="sm").style(f"color: {COLORS['accent']}")
                    ui.label("Components").classes("text-sm font-semibold").style(
                        f"color: {COLORS['text_primary']}"
                    )
                    status_badge(components_status)
                ui.label(f"{len(components_list)} registered").classes("text-xs").style(
                    f"color: {COLORS['text_muted']}"
                )

        # -- Row 2: Quality metrics --
        quality = results.get("quality") or {}
        ui.label("Data Quality").classes("section-title mt-4")
        with ui.row().classes("gap-4 flex-wrap"):
            total = quality.get("total_evaluations", 0)
            pass_rate = quality.get("pass_rate", 0)
            avg_score = quality.get("average_score", 0)

            metric_card("Total Evaluations", total)
            metric_card(
                "Pass Rate",
                f"{pass_rate:.0%}" if isinstance(pass_rate, float) else str(pass_rate),
                color=(
                    COLORS["success"]
                    if (isinstance(pass_rate, (int, float)) and pass_rate >= 0.8)
                    else COLORS["warning"]
                ),
            )
            metric_card(
                "Avg Score",
                f"{avg_score:.1f}" if isinstance(avg_score, float) else str(avg_score),
            )

        # -- Row 3: Components list --
        if components_list:
            ui.label("Registered Components").classes("section-title mt-4")
            with (
                ui.card().classes("dex-card"),
                ui.grid(columns=2).classes("gap-x-8 gap-y-2"),
            ):
                for comp in components_list:
                    name = comp.get("name", "—")
                    status = comp.get("status", "unknown")
                    ui.label(name).classes("text-xs font-mono").style(
                        f"color: {COLORS['text_muted']}"
                    )
                    ui.label(status).classes("text-sm").style(f"color: {COLORS['text_primary']}")
