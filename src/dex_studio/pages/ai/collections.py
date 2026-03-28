"""AI Collections page — vector store collections (coming soon).

Route: ``/ai/collections``

Depends on vector store endpoints not yet wired in the DEX engine.
Renders a placeholder until those endpoints are available.
"""

from __future__ import annotations

import logging

from nicegui import ui

from dex_studio.app import get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/ai/collections")
async def ai_collections_page() -> None:
    """Render the AI collections placeholder page."""
    apply_global_styles(get_theme())

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/collections")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Collections")
            with ui.column().classes("p-6 gap-4 w-full"):
                empty_state(
                    "Collections — coming soon",
                    icon="collections_bookmark",
                )
