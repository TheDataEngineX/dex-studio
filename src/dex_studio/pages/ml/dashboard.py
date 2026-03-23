"""ML domain dashboard — overview of experiments and models.

Route: ``/ml``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.metric_card import metric_card
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


@ui.page("/ml")
async def ml_dashboard_page() -> None:
    """Render the ML domain dashboard."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Dashboard")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                ui.label("Overview").classes("section-title")

                experiments_data: dict[str, Any] = {}
                models_data: dict[str, Any] = {}

                try:
                    experiments_data = await client.list_experiments()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch experiments: %s", exc)

                try:
                    models_data = await client.list_models()
                except DexAPIError as exc:
                    _log.warning("Failed to fetch models: %s", exc)

                experiments_count: str | int
                if experiments_data:
                    exps = experiments_data.get("experiments", [])
                    experiments_count = len(exps) if isinstance(exps, list) else "—"
                else:
                    experiments_count = "—"

                models_count: str | int
                if models_data:
                    models = models_data.get("models", [])
                    models_count = len(models) if isinstance(models, list) else "—"
                else:
                    models_count = "—"

                with ui.row().classes("gap-4 flex-wrap"):
                    metric_card("Experiments", experiments_count)
                    metric_card("Models", models_count)
