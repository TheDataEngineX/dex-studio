"""AI Retrieval page — hybrid retrieval interface (coming soon).

Route: ``/ai/retrieval``

Depends on retrieval endpoints not yet fully wired in the DEX engine.
Renders a placeholder until those endpoints are available.
"""

from __future__ import annotations

import logging

from nicegui import ui

from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/ai/retrieval")
async def ai_retrieval_page() -> None:
    """Render the AI retrieval placeholder page."""
    apply_global_styles()

    app_shell(active_domain="ai")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ai", active_route="/ai/retrieval")
        with ui.column().classes("flex-1"):
            breadcrumb("AI", "Retrieval")
            with ui.column().classes("p-6 gap-4 w-full"):
                empty_state(
                    "Retrieval — coming soon",
                    icon="search",
                )
