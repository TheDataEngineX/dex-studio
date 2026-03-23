"""ML features page — feature store browser and entity lookup.

Route: ``/ml/features``
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from dex_studio.client import DexAPIError, DexClient
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.data_table import data_table
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_INPUT_PROPS = "outlined dark"

_GROUP_COLUMNS: list[dict[str, Any]] = [
    {"name": "name", "label": "Group", "field": "name", "align": "left"},
    {"name": "entity_key", "label": "Entity Key", "field": "entity_key", "align": "left"},
    {"name": "feature_count", "label": "Features", "field": "feature_count", "align": "right"},
    {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
]


def _columns_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build table column defs from a single row dict's keys."""
    return [
        {
            "name": k,
            "label": k.replace("_", " ").title(),
            "field": k,
            "align": "left",
        }
        for k in row
    ]


def _render_groups(groups: list[dict[str, Any]]) -> None:
    """Render the feature groups section."""
    ui.label("Feature Groups").classes("section-title")
    if not groups:
        empty_state("No feature groups found", icon="dataset")
        return
    rows = [
        {
            "name": g.get("name", "—"),
            "entity_key": g.get("entity_key", "—"),
            "feature_count": g.get("feature_count", 0),
            "updated_at": g.get("updated_at", "—"),
        }
        for g in groups
    ]
    data_table(_GROUP_COLUMNS, rows, title="Feature Groups")


@ui.page("/ml/features")
async def ml_features_page() -> None:
    """Render the ML feature store page."""
    apply_global_styles()
    client: DexClient | None = app.storage.general.get("client")

    app_shell(active_domain="ml")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("ml", active_route="/ml/features")
        with ui.column().classes("flex-1"):
            breadcrumb("ML", "Feature Store")
            with ui.column().classes("p-6 gap-4 w-full"):
                if client is None:
                    ui.label("No connection configured.").style(f"color: {COLORS['error']}")
                    return

                groups: list[dict[str, Any]] = []
                try:
                    resp = await client.list_feature_groups()
                    groups = resp.get("groups", [])
                except DexAPIError as exc:
                    ui.label(f"Error fetching feature groups: {exc}").style(
                        f"color: {COLORS['error']}"
                    )

                _render_groups(groups)

                # -- Entity lookup --
                ui.label("Entity Lookup").classes("section-title mt-6")
                ui.label("Retrieve features for specific entity IDs from a feature group.").classes(
                    "text-xs"
                ).style(f"color: {COLORS['text_muted']}")

                group_names = [g.get("name", "") for g in groups if g.get("name")]
                if group_names:
                    lookup_group: ui.select | ui.input = (
                        ui.select(label="Feature Group", options=group_names)
                        .classes("w-64")
                        .props(_INPUT_PROPS)
                    )
                else:
                    lookup_group = (
                        ui.input(
                            label="Feature Group",
                            placeholder="e.g. user_features",
                        )
                        .classes("w-64")
                        .props(_INPUT_PROPS)
                    )

                entity_ids_input = (
                    ui.input(
                        label="Entity IDs (comma-separated)",
                        placeholder="e.g. user_1,user_2",
                    )
                    .classes("w-96")
                    .props(_INPUT_PROPS)
                )

                lookup_container = ui.column().classes("w-full mt-2")

                async def lookup_features() -> None:
                    group_name: str = lookup_group.value or ""
                    raw_ids = entity_ids_input.value.strip()
                    if not group_name:
                        return
                    entity_ids = (
                        [e.strip() for e in raw_ids.split(",") if e.strip()] if raw_ids else None
                    )
                    lookup_container.clear()
                    with lookup_container:
                        try:
                            result = await client.get_features(group_name, entity_ids)
                        except DexAPIError as exc:
                            ui.label(f"Error: {exc}").style(f"color: {COLORS['error']}")
                            return
                        features_list: list[dict[str, Any]] = result.get("features", [])
                        if not features_list:
                            empty_state(
                                "No features found for these entities",
                                icon="search_off",
                            )
                            return
                        cols = _columns_from_row(features_list[0])
                        data_table(cols, features_list, title="Feature Values")

                ui.button(
                    "Lookup",
                    icon="search",
                    on_click=lookup_features,
                ).props("color=indigo").classes("mt-2")
