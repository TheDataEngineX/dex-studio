"""Project Hub — launch screen with project list."""

from __future__ import annotations

from nicegui import ui

from dex_studio.components.project_card import project_card
from dex_studio.config import ProjectEntry, load_projects
from dex_studio.theme import COLORS, apply_global_styles

__all__ = ["project_hub_page"]


@ui.page("/")
async def project_hub_page() -> None:
    """Render the project hub landing page."""
    apply_global_styles()

    projects: list[ProjectEntry] = load_projects()

    with ui.column().classes("items-center justify-center w-full").style("padding: 40px;"):
        ui.label("⬡ DEX Studio").style(
            f"font-size: 28px; font-weight: 700; color: {COLORS['accent']};"
        )
        ui.label("Unified Data + ML + AI Platform").style(
            f"font-size: 14px; color: {COLORS['text_dim']}; margin-top: 4px;"
        )

        with ui.row().classes("gap-3 mt-8"):
            ui.button("+ New Project").style(
                f"background: {COLORS['accent']}; color: white; border-radius: 8px;"
            )
            ui.button("Import dex.yaml").props("outline").style("border-radius: 8px;")

        if projects:
            ui.label("RECENT PROJECTS").classes("section-title mt-8 mb-3")
            with ui.column().classes("w-full gap-2").style("max-width: 720px;"):
                for proj in projects:
                    project_card(
                        proj,
                        on_click=lambda p=proj: ui.navigate.to(f"/data?project={p.name}"),
                    )
        else:
            from dex_studio.components.empty_state import empty_state

            empty_state(
                message="No projects configured yet",
                icon="folder_open",
                action_label="+ New Project",
            )
