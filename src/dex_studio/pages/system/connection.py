"""System connection page — multi-project connection manager.

Route: ``/system/connection``
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from nicegui import ui

from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.empty_state import empty_state
from dex_studio.config import ProjectEntry, load_projects, save_projects
from dex_studio.theme import COLORS, apply_global_styles

_log = logging.getLogger(__name__)


def _make_remove_handler(
    name: str,
    projects_state: dict[str, list[ProjectEntry]],
    refresh: Callable[[], None],
) -> Callable[[], None]:
    """Return a closure that removes *name* from the project list."""

    def _remove() -> None:
        projects_state["items"] = [p for p in projects_state["items"] if p.name != name]
        save_projects(projects_state["items"])
        refresh()

    return _remove


def _render_project_card(
    proj: ProjectEntry,
    projects_state: dict[str, list[ProjectEntry]],
    refresh: Callable[[], None],
) -> None:
    """Render a single project card with name, URL and delete button."""
    with ui.card().classes("dex-card").style("padding: 14px; max-width: 560px;"):  # noqa: SIM117
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.icon(proj.icon or "folder").style(f"color: {COLORS['accent']}; font-size: 20px;")
                with ui.column().classes("gap-0"):
                    ui.label(proj.name).classes("text-sm font-semibold").style(
                        f"color: {COLORS['text_primary']}"
                    )
                    ui.label(proj.url).classes("text-xs font-mono").style(
                        f"color: {COLORS['text_muted']}"
                    )

            ui.button(
                icon="delete",
                on_click=_make_remove_handler(proj.name, projects_state, refresh),
            ).props("flat round").style(f"color: {COLORS['error']}; font-size: 16px;")


@ui.page("/system/connection")
async def system_connection_page() -> None:
    """Render the multi-project connection manager page."""
    apply_global_styles()

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/connection")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Connection")
            with ui.column().classes("p-6 gap-4 w-full"):
                ui.label("Project Connections").classes("text-lg font-semibold").style(
                    f"color: {COLORS['text_primary']}"
                )

                projects_state: dict[str, list[ProjectEntry]] = {"items": load_projects()}
                project_list_container = ui.column().classes("w-full gap-3")

                def _render_project_list() -> None:
                    project_list_container.clear()
                    with project_list_container:
                        if not projects_state["items"]:
                            empty_state(
                                "No projects configured — add one below",
                                icon="lan",
                            )
                            return
                        for proj in projects_state["items"]:
                            _render_project_card(proj, projects_state, _render_project_list)

                _render_project_list()

                # -- Add project form --
                ui.label("Add Project").classes("section-title mt-2")
                with ui.card().classes("dex-card").style("padding: 16px; max-width: 560px;"):
                    name_input = ui.input(placeholder="Project name").style(
                        f"background: {COLORS['bg_secondary']}; "
                        f"color: {COLORS['text_primary']}; width: 100%;"
                    )
                    url_input = ui.input(placeholder="http://localhost:17000").style(
                        f"background: {COLORS['bg_secondary']}; "
                        f"color: {COLORS['text_primary']}; width: 100%;"
                    )
                    form_error = ui.label("").classes("text-xs").style(f"color: {COLORS['error']}")

                    def _add_project() -> None:
                        name_val = (name_input.value or "").strip()
                        url_val = (url_input.value or "").strip()

                        if not name_val:
                            form_error.set_text("Project name is required.")
                            return
                        if not url_val:
                            form_error.set_text("Project URL is required.")
                            return

                        existing = {p.name for p in projects_state["items"]}
                        if name_val in existing:
                            form_error.set_text(f"A project named '{name_val}' already exists.")
                            return

                        form_error.set_text("")
                        new_proj = ProjectEntry(name=name_val, url=url_val)
                        projects_state["items"] = [*projects_state["items"], new_proj]
                        save_projects(projects_state["items"])
                        name_input.set_value("")
                        url_input.set_value("")
                        _render_project_list()

                    ui.button("Add Project", icon="add", on_click=_add_project).props("flat").style(
                        f"color: {COLORS['accent']}"
                    )
