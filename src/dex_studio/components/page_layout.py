"""Page layout wrapper — sidebar + main content area.

Every page should call ``page_layout()`` as a context manager to get
the standard sidebar + content grid.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import ui

from dex_studio.components.sidebar import render_sidebar
from dex_studio.theme import COLORS, apply_global_styles

__all__ = ["page_layout"]


@contextmanager
def page_layout(
    title: str,
    active_route: str = "/",
) -> Generator[ui.column, None, None]:
    """Wrap page content in the standard DEX Studio layout.

    Yields a ``ui.column`` representing the main content area.

    Usage::

        with page_layout("Overview", active_route="/") as content:
            ui.label("Hello from DEX Studio")
    """
    apply_global_styles()

    with ui.row().classes("w-full min-h-screen no-wrap").style("gap: 0"):
        render_sidebar(active_route=active_route)

        with ui.column().classes("flex-grow p-6 gap-4 overflow-auto") as content:
            # Page header
            ui.label(title).classes("text-2xl font-bold").style(
                f"color: {COLORS['text_primary']}"
            )
            ui.separator().style(f"background-color: {COLORS['divider']}")
            yield content
