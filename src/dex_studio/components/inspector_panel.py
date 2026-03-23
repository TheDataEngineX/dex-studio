"""Inspector panel — collapsible right panel for detail views."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["inspector_panel"]


@contextmanager
def inspector_panel(
    title: str = "Inspector",
    width: int = 280,
) -> Generator[ui.column]:
    """Render a collapsible right inspector panel. Yields a column for content."""
    with ui.column().style(
        f"width: {width}px; background: {COLORS['bg_sidebar']}; "
        f"border-left: 1px solid {COLORS['border']}; overflow-y: auto;"
    ):
        ui.label(title).style(
            f"padding: 12px 16px; border-bottom: 1px solid {COLORS['border']}; "
            f"font-size: 12px; font-weight: 600;"
        )
        content = ui.column().classes("w-full")
        yield content
