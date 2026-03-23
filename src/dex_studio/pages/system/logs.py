"""System logs page — structured log viewer with filtering.

Route: ``/system/logs``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_LOG_LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"]

_LEVEL_COLORS: dict[str, str] = {
    "debug": COLORS["text_dim"],
    "info": COLORS["text_muted"],
    "warning": COLORS["warning"],
    "error": COLORS["error"],
    "critical": COLORS["error"],
}


def _level_color(level: str) -> str:
    return _LEVEL_COLORS.get(level.lower(), COLORS["text_muted"])


def _render_log_entry(entry: dict[str, Any]) -> None:
    """Render a single log entry row."""
    entry_level: str = entry.get("level", "info")
    timestamp: str = entry.get("timestamp", "")
    message: str = entry.get("message", str(entry))
    component: str = entry.get("component", "")
    color = _level_color(entry_level)

    with (
        ui.row()
        .classes("items-start gap-2 py-1")
        .style(
            f"border-bottom: 1px solid {COLORS['divider']}; "
            "font-family: monospace; font-size: 12px;"
        )
    ):
        if timestamp:
            ui.label(timestamp).style(f"color: {COLORS['text_dim']}; min-width: 180px;")
        ui.label(entry_level.upper()).style(f"color: {color}; min-width: 70px; font-weight: 600;")
        if component:
            ui.label(f"[{component}]").style(f"color: {COLORS['accent_light']}; min-width: 120px;")
        ui.label(message).style(f"color: {COLORS['text_primary']}; flex: 1;")


@ui.page("/system/logs")
async def system_logs_page() -> None:
    """Render the structured log viewer page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/logs")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Logs")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                # -- Filter controls --
                ui.label("Filters").classes("section-title")

                with ui.row().classes("items-end gap-4 flex-wrap"):
                    with ui.column().classes("gap-1"):
                        ui.label("Level").classes("text-xs").style(f"color: {COLORS['text_muted']}")
                        level_select = ui.select(
                            _LOG_LEVELS,
                            value="ALL",
                        ).style(
                            f"background: {COLORS['bg_secondary']}; "
                            f"color: {COLORS['text_primary']}; min-width: 120px;"
                        )

                    with ui.column().classes("gap-1"):
                        ui.label("Limit").classes("text-xs").style(f"color: {COLORS['text_muted']}")
                        limit_input = ui.number(value=100, min=10, max=1000, step=10).style(
                            f"background: {COLORS['bg_secondary']}; "
                            f"color: {COLORS['text_primary']}; width: 100px;"
                        )

                    refresh_btn = (
                        ui.button("Refresh", icon="refresh")
                        .props("flat")
                        .style(f"color: {COLORS['accent']}")
                    )

                # -- Log output area --
                ui.label("Log Entries").classes("section-title mt-2")
                log_container = ui.column().classes("w-full gap-1")

                async def _load_logs() -> None:
                    level_val = str(level_select.value)
                    limit_val = int(limit_input.value or 100)
                    api_level: str | None = None if level_val == "ALL" else level_val

                    log_container.clear()

                    try:
                        resp = await client.logs(level=api_level, limit=limit_val)
                    except DexAPIError as exc:
                        _log.warning("Failed to fetch logs: %s", exc)
                        with log_container:
                            ui.label(f"Error fetching logs: {exc}").style(
                                f"color: {COLORS['error']}"
                            )
                        return

                    entries: list[dict[str, Any]] = resp.get("logs", [])
                    if not isinstance(entries, list):
                        entries = []

                    if not entries:
                        with log_container:
                            empty_state("No log entries found", icon="article")
                        return

                    with log_container:
                        for entry in entries:
                            _render_log_entry(entry)

                refresh_btn.on_click(_load_logs)

                # Initial load
                await _load_logs()
