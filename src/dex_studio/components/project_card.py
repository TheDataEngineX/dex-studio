"""Project card — used in project hub and switcher dropdown."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dex_studio.config import ProjectEntry
from dex_studio.theme import COLORS

__all__ = ["project_card"]


def project_card(project: ProjectEntry, *, on_click: Any = None) -> None:
    """Render a project card for the hub."""
    with (  # noqa: SIM117
        ui.card()
        .classes("dex-card w-full cursor-pointer")
        .style("padding: 16px;")
        .on("click", on_click)
    ):
        with ui.row().classes("items-center gap-4 w-full"):
            ui.icon(project.icon or "folder").style(f"font-size: 24px; color: {COLORS['accent']};")
            with ui.column().classes("flex-1"):
                ui.label(project.name).style("font-weight: 600; font-size: 14px;")
                ui.label(project.url).style(f"font-size: 12px; color: {COLORS['text_dim']};")
