"""Project Hub — launch screen with project list and CRUD."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from dex_studio.app import get_theme
from dex_studio.components.project_card import project_card
from dex_studio.config import ProjectEntry, load_projects, save_projects
from dex_studio.theme import apply_global_styles, get_colors

__all__ = ["project_hub_page"]


def _project_form_dialog(
    title: str,
    initial: ProjectEntry | None,
    on_save: Callable[[ProjectEntry], None],
) -> ui.dialog:
    """Return a dialog for creating or editing a project."""
    dlg = ui.dialog()
    with dlg, ui.card().style("min-width: 420px; padding: 24px;"):
        colors = get_colors(get_theme())
        ui.label(title).style(
            f"font-size: 16px; font-weight: 600; color: {colors['text_primary']};"
            " margin-bottom: 12px;"
        )
        name_input = ui.input(
            "Project name",
            value=initial.name if initial else "",
            placeholder="e.g. my-project",
        ).classes("w-full")
        url_input = ui.input(
            "Engine URL",
            value=initial.url if initial else "http://localhost:17000",
        ).classes("w-full")
        token_input = ui.input(
            "Auth token (optional)",
            value=initial.token or "" if initial else "",
            password=True,
            password_toggle_button=True,
        ).classes("w-full")
        error_label = ui.label("").style(f"color: {colors['error']}; font-size: 12px;")

        def _save() -> None:
            name = name_input.value.strip()
            url = url_input.value.strip()
            if not name:
                error_label.set_text("Name is required.")
                return
            if not url:
                error_label.set_text("URL is required.")
                return
            on_save(ProjectEntry(name=name, url=url, token=token_input.value.strip() or None))
            dlg.close()

        with ui.row().classes("justify-end gap-2 mt-4"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            ui.button("Save", on_click=_save).style(
                f"background: {colors['accent']}; color: white;"
            )
    return dlg


def _confirm_dialog(message: str, on_confirm: Callable[[], None]) -> ui.dialog:
    """Return a yes/no confirmation dialog."""
    dlg = ui.dialog()
    with dlg, ui.card().style("padding: 24px; min-width: 320px;"):
        colors = get_colors(get_theme())
        ui.label(message).style(f"color: {colors['text_primary']}; font-size: 14px;")

        def _do_confirm() -> None:
            on_confirm()
            dlg.close()

        with ui.row().classes("justify-end gap-2 mt-4"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            ui.button("Delete", on_click=_do_confirm).style(
                f"background: {colors['error']}; color: white;"
            )
    return dlg


def _project_row(
    proj: ProjectEntry,
    colors: dict[str, str],
    on_edit: Callable[[ProjectEntry], None],
    on_delete: Callable[[ProjectEntry], None],
) -> None:
    """Render a single project row with edit/delete buttons."""
    with ui.row().classes("w-full items-center gap-2"):
        with ui.element("div").classes("flex-1"):
            project_card(
                proj,
                on_click=lambda p=proj: ui.navigate.to(f"/data?project={p.name}"),
            )
        ui.button(icon="edit", on_click=lambda p=proj: on_edit(p)).props("flat round").style(
            f"color: {colors['text_muted']};"
        )
        ui.button(icon="delete", on_click=lambda p=proj: on_delete(p)).props("flat round").style(
            f"color: {colors['error']};"
        )


def _handle_new(on_refresh: Callable[[], None]) -> None:
    def _on_save(entry: ProjectEntry) -> None:
        save_projects([*load_projects(), entry])
        on_refresh()

    _project_form_dialog("New Project", None, _on_save).open()


def _handle_edit(proj: ProjectEntry, on_refresh: Callable[[], None]) -> None:
    def _on_save(updated: ProjectEntry) -> None:
        save_projects([updated if p.name == proj.name else p for p in load_projects()])
        on_refresh()

    _project_form_dialog(f"Edit — {proj.name}", proj, _on_save).open()


def _handle_delete(proj: ProjectEntry, on_refresh: Callable[[], None]) -> None:
    def _on_confirm() -> None:
        save_projects([p for p in load_projects() if p.name != proj.name])
        on_refresh()

    _confirm_dialog(f"Delete project '{proj.name}'? This cannot be undone.", _on_confirm).open()


@ui.page("/")
async def project_hub_page() -> None:
    """Render the project hub landing page."""
    apply_global_styles(get_theme())
    colors = get_colors(get_theme())
    projects: list[ProjectEntry] = load_projects()
    refresh = ui.navigate.reload

    with ui.column().classes("items-center w-full").style("padding: 40px;"):
        ui.label("⬡ DEX Studio").style(
            f"font-size: 28px; font-weight: 700; color: {colors['accent']};"
        )
        ui.label("Unified Data + ML + AI Platform").style(
            f"font-size: 14px; color: {colors['text_dim']}; margin-top: 4px;"
        )
        with ui.row().classes("gap-3 mt-8"):
            ui.button("+ New Project", on_click=lambda: _handle_new(refresh)).style(
                f"background: {colors['accent']}; color: white; border-radius: 8px;"
            )

        if projects:
            ui.label("RECENT PROJECTS").classes("section-title mt-8 mb-3")
            with ui.column().classes("w-full gap-2").style("max-width: 720px;"):
                for proj in projects:
                    _project_row(
                        proj,
                        colors,
                        on_edit=lambda p=proj: _handle_edit(p, refresh),
                        on_delete=lambda p=proj: _handle_delete(p, refresh),
                    )
        else:
            from dex_studio.components.empty_state import empty_state

            empty_state(
                message="No projects configured yet",
                icon="folder_open",
                action_label="+ New Project",
                on_action=lambda: _handle_new(refresh),
            )
