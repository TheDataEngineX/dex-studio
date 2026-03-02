"""Sidebar navigation component.

Renders the persistent left sidebar with navigation links, connection
status indicator, and DEX Studio branding.
"""

from __future__ import annotations

from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.theme import COLORS

__all__ = ["render_sidebar"]

_NAV_ITEMS: list[tuple[str, str, str]] = [
    # (label, icon, route)
    ("Overview", "dashboard", "/"),
    ("Health", "monitor_heart", "/health"),
    ("Data Quality", "verified", "/quality"),
    ("Lineage", "account_tree", "/lineage"),
    ("ML Models", "model_training", "/models"),
    ("Settings", "settings", "/settings"),
]


def render_sidebar(active_route: str = "/") -> None:
    """Render the sidebar into the current NiceGUI page layout."""
    with ui.column().classes("sidebar-nav w-56 min-h-screen flex-shrink-0"):
        # Brand
        with ui.row().classes("items-center gap-2 px-5 py-4 mb-2"):
            ui.icon("hub", size="sm").style(f"color: {COLORS['accent']}")
            ui.label("DEX Studio").classes("text-lg font-bold").style(
                f"color: {COLORS['text_primary']}"
            )

        ui.separator().style(f"background-color: {COLORS['divider']}")

        # Nav links
        for label, icon, route in _NAV_ITEMS:
            is_active = route == active_route
            classes = "sidebar-link"
            if is_active:
                classes += " active"

            with ui.link(target=route).classes(classes).style("text-decoration: none"):
                ui.icon(icon, size="xs").style(
                    f"color: {COLORS['accent_light'] if is_active else COLORS['text_muted']}"
                )
                ui.label(label)

        # Spacer
        ui.space()

        # Connection status (bottom)
        ui.separator().style(f"background-color: {COLORS['divider']}")
        with ui.row().classes("items-center gap-2 px-5 py-3"):
            status_dot = ui.icon("circle", size="2xs")
            status_label = ui.label("Checking…").classes("text-xs").style(
                f"color: {COLORS['text_muted']}"
            )

        async def _check_connection() -> None:
            client: DexClient | None = app.storage.general.get("client")
            if client and await client.ping():
                status_dot.style(f"color: {COLORS['success']}")
                status_label.set_text("Connected")
            else:
                status_dot.style(f"color: {COLORS['error']}")
                status_label.set_text("Disconnected")

        ui.timer(interval=5.0, callback=_check_connection, once=False)
