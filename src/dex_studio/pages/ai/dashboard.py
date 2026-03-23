"""AI domain dashboard — overview metrics for agents and tools.

Route: ``/ai``

Drives DEX engine endpoints:
    GET /api/v1/ai/agents  → list registered agents
    GET /api/v1/ai/tools   → list registered tools
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components import metric_card
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/ai")
async def ai_dashboard_page() -> None:
    """Render the AI domain dashboard."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                results: dict[str, Any] = {}
                errors: list[str] = []

                async def _fetch(key: str, coro: Any) -> None:
                    try:
                        results[key] = await coro
                    except DexAPIError as exc:
                        errors.append(f"{key}: {exc}")
                        results[key] = None

                await asyncio.gather(
                    _fetch("agents", client.list_agents()),
                    _fetch("tools", client.list_tools()),
                )

                if errors:
                    with (
                        ui.card()
                        .classes("dex-card w-full")
                        .style(f"border-color: {COLORS['warning']}")
                    ):
                        ui.label("Some endpoints unreachable").classes(
                            "font-semibold text-sm"
                        ).style(f"color: {COLORS['warning']}")
                        for err in errors:
                            ui.label(f"• {err}").classes("text-xs").style(
                                f"color: {COLORS['text_muted']}"
                            )

                agents_resp = results.get("agents") or {}
                agents: list[dict[str, Any]] = agents_resp.get("agents", [])

                tools_resp = results.get("tools") or {}
                tools: list[dict[str, Any]] = tools_resp.get("tools", [])

                ui.label("AI Overview").classes("section-title")
                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Agents", len(agents))
                    metric_card("Tools", len(tools))

                if agents:
                    ui.label("Registered Agents").classes("section-title mt-4")
                    with (
                        ui.card().classes("dex-card w-full"),
                        ui.grid(columns=2).classes("gap-x-8 gap-y-2"),
                    ):
                        for agent in agents:
                            name = agent.get("name", "—")
                            status = agent.get("status", "unknown")
                            ui.label(name).classes("text-xs font-mono").style(
                                f"color: {COLORS['text_muted']}"
                            )
                            ui.label(status).classes("text-sm").style(
                                f"color: {COLORS['text_primary']}"
                            )
