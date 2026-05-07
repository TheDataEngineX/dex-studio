# src/dex_studio/components/breadcrumb.py
"""Breadcrumb — context navigation bar."""

from __future__ import annotations

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["breadcrumb"]


def breadcrumb(*parts: str) -> None:
    """Render breadcrumb from path parts. Last part is active (white), rest are dim."""
    with (
        ui.row()
        .classes("items-center gap-1")
        .style(
            f"padding: 10px 24px; border-bottom: 1px solid {COLORS['divider']}; font-size: 12px;"
        )
    ):
        for i, part in enumerate(parts):
            if i > 0:
                ui.label("›").style(f"color: {COLORS['text_dim']}; margin: 0 6px")
            is_last = i == len(parts) - 1
            color = COLORS["text_primary"] if is_last else COLORS["text_dim"]
            ui.label(part).style(f"color: {color}")
