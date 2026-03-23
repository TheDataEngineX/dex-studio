"""App shell — top bar with domain tabs, project switcher, command palette trigger."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["app_shell"]

DOMAINS = [
    {"name": "Data", "key": "data", "route": "/data"},
    {"name": "ML", "key": "ml", "route": "/ml"},
    {"name": "AI", "key": "ai", "route": "/ai"},
    {"name": "System", "key": "system", "route": "/system"},
]


def app_shell(active_domain: str = "data", project_name: str = "default") -> None:
    """Render the top navigation bar."""
    with (
        ui.row()
        .classes("w-full items-center justify-between")
        .style(
            f"padding: 8px 16px; background: {COLORS['bg_secondary']}; "
            f"border-bottom: 1px solid {COLORS['border']};"
        )
    ):
        with ui.row().classes("items-center gap-6"):
            ui.label("⬡ DEX Studio").style(
                f"font-weight: 700; font-size: 15px; color: {COLORS['accent']};"
            )
            with (
                ui.row()
                .classes("items-center gap-2")
                .style(
                    f"padding: 5px 12px; background: {COLORS['border']}; "
                    "border-radius: 6px; cursor: pointer;"
                )
            ):
                ui.label(project_name).style("font-weight: 500; font-size: 13px;")
                ui.label("▾").style(f"color: {COLORS['text_dim']};")
            ui.element("div").style(f"width: 1px; height: 20px; background: {COLORS['border']};")
            with ui.row().classes("gap-1"):
                for domain in DOMAINS:
                    is_active = domain["key"] == active_domain
                    style = (
                        "padding: 6px 14px; border-radius: 6px; font-size: 12px; "
                        "cursor: pointer; text-decoration: none; "
                    )
                    if is_active:
                        style += f"background: {COLORS['accent']}; color: white; font-weight: 600;"
                    else:
                        style += f"color: {COLORS['text_muted']};"
                    ui.link(domain["name"], target=domain["route"]).style(style)

        with ui.row().classes("items-center gap-3"):  # noqa: SIM117
            with (
                ui.row()
                .classes("items-center gap-2")
                .style(
                    f"padding: 5px 12px; background: {COLORS['border']}; border-radius: 6px; "
                    f"color: {COLORS['text_dim']}; font-size: 12px; min-width: 180px;"
                )
            ):
                ui.label("⌘ Search...").style(f"color: {COLORS['text_dim']};")
                ui.label("Ctrl+K").style(
                    f"margin-left: auto; background: {COLORS['bg_hover']}; "
                    "padding: 1px 6px; border-radius: 3px; font-size: 10px;"
                )
