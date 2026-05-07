"""Per-domain section sidebar — changes based on active domain tab."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from dex_studio.theme import COLORS

__all__ = ["domain_sidebar"]

DOMAIN_SECTIONS: dict[str, list[dict[str, Any]]] = {
    "data": [
        {
            "section": "Overview",
            "items": [
                {"label": "Dashboard", "route": "/data", "icon": "dashboard"},
            ],
        },
        {
            "section": "Operations",
            "items": [
                {"label": "Pipelines", "route": "/data/pipelines", "icon": "account_tree"},
                {"label": "Sources", "route": "/data/sources", "icon": "storage"},
                {"label": "Warehouse", "route": "/data/warehouse", "icon": "warehouse"},
            ],
        },
        {
            "section": "Observability",
            "items": [
                {"label": "Quality Gates", "route": "/data/quality", "icon": "verified"},
                {"label": "Lineage", "route": "/data/lineage", "icon": "timeline"},
            ],
        },
    ],
    "ml": [
        {
            "section": "Overview",
            "items": [
                {"label": "Dashboard", "route": "/ml", "icon": "dashboard"},
            ],
        },
        {
            "section": "Lifecycle",
            "items": [
                {"label": "Experiments", "route": "/ml/experiments", "icon": "science"},
                {"label": "Models", "route": "/ml/models", "icon": "model_training"},
                {"label": "Predictions", "route": "/ml/predictions", "icon": "psychology"},
            ],
        },
        {
            "section": "Features",
            "items": [
                {"label": "Feature Store", "route": "/ml/features", "icon": "dataset"},
                {"label": "Drift Monitor", "route": "/ml/drift", "icon": "trending_up"},
            ],
        },
    ],
    "ai": [
        {
            "section": "Overview",
            "items": [
                {"label": "Dashboard", "route": "/ai", "icon": "dashboard"},
            ],
        },
        {
            "section": "Agents",
            "items": [
                {"label": "Agent Chat", "route": "/ai/agents", "icon": "smart_toy"},
                {"label": "Tools", "route": "/ai/tools", "icon": "build"},
            ],
        },
        {
            "section": "Knowledge",
            "items": [
                {
                    "label": "Collections",
                    "route": "/ai/collections",
                    "icon": "collections_bookmark",
                },
                {"label": "Retrieval", "route": "/ai/retrieval", "icon": "search"},
            ],
        },
    ],
    "system": [
        {
            "section": "Health",
            "items": [
                {"label": "Status", "route": "/system", "icon": "monitor_heart"},
                {"label": "Components", "route": "/system/components", "icon": "developer_board"},
            ],
        },
        {
            "section": "Observability",
            "items": [
                {"label": "Metrics", "route": "/system/metrics", "icon": "bar_chart"},
                {"label": "Logs", "route": "/system/logs", "icon": "article"},
                {"label": "Traces", "route": "/system/traces", "icon": "timeline"},
            ],
        },
        {
            "section": "Config",
            "items": [
                {"label": "Settings", "route": "/system/settings", "icon": "settings"},
                {"label": "Connection", "route": "/system/connection", "icon": "lan"},
            ],
        },
    ],
}


def domain_sidebar(domain: str, active_route: str = "") -> None:
    """Render the section sidebar for a given domain."""
    sections = DOMAIN_SECTIONS.get(domain, [])
    with (
        ui.column()
        .classes("w-full")
        .style(
            f"width: 200px; background: {COLORS['bg_sidebar']}; "
            f"border-right: 1px solid {COLORS['border']}; padding: 12px 0; min-height: 100vh;"
        )
    ):
        for section in sections:
            ui.label(section["section"]).classes("section-title").style(
                "padding: 4px 16px; margin-top: 12px;"
            )
            for item in section["items"]:
                is_active = active_route == item["route"]
                bg = (
                    f"background: {COLORS['bg_hover']}; border-left: 2px solid {COLORS['accent']};"
                    if is_active
                    else ""
                )
                text_color = COLORS["text_primary"] if is_active else COLORS["text_muted"]
                style = (
                    f"padding: 8px 16px; font-size: 13px; cursor: pointer; "
                    f"color: {text_color}; {bg}"
                )
                with ui.link(target=item["route"]).style("text-decoration: none;"):  # noqa: SIM117
                    with ui.row().classes("items-center gap-2").style(style):
                        ui.icon(item["icon"]).style("font-size: 16px;")
                        ui.label(item["label"])
