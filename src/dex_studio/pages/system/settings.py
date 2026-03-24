"""System settings page — engine config summary, theme toggle, UI preferences.

Route: ``/system/settings``
"""

from __future__ import annotations

import logging

from nicegui import ui

from dex_studio.app import get_engine, get_studio_config, get_theme
from dex_studio.components.app_shell import app_shell
from dex_studio.components.breadcrumb import breadcrumb
from dex_studio.components.domain_sidebar import domain_sidebar
from dex_studio.components.status_badge import status_badge
from dex_studio.config import StudioConfig, save_config
from dex_studio.engine import DexEngine
from dex_studio.theme import COLORS, LIGHT_COLORS, apply_global_styles

_log = logging.getLogger(__name__)

_SECTION_HEADING = "text-lg font-semibold"
_CARD_STYLE = "padding: 20px; max-width: 600px;"


@ui.page("/system/settings")
async def system_settings_page() -> None:
    """Render the system settings page."""
    theme = get_theme()
    apply_global_styles(theme)
    colors = LIGHT_COLORS if theme == "light" else COLORS

    engine: DexEngine | None = get_engine()
    config: StudioConfig | None = get_studio_config()

    app_shell(active_domain="system")
    with ui.row().classes("w-full flex-1").style("min-height: calc(100vh - 50px);"):
        domain_sidebar("system", active_route="/system/settings")
        with ui.column().classes("flex-1"):
            breadcrumb("System", "Settings")
            with ui.column().classes("p-6 gap-6 w-full"):
                # ── Engine config ────────────────────────────────────────
                ui.label("Engine Configuration").classes(_SECTION_HEADING).style(
                    f"color: {colors['text_primary']}"
                )
                if engine is not None:
                    with ui.card().classes("dex-card").style(_CARD_STYLE):
                        ui.label("Engine").classes("section-title")
                        with ui.grid(columns=2).classes("gap-x-8 gap-y-3 mt-2"):
                            _row("Project", engine.config.project.name, colors)
                            _row("Config Path", str(engine.config_path), colors)
                            _row("Project Dir", str(engine.project_dir), colors)
                            _row("Data Engine", engine.config.data.engine, colors)
                            _row(
                                "Pipelines",
                                str(len(engine.config.data.pipelines)),
                                colors,
                            )
                            _row(
                                "Sources",
                                str(len(engine.config.data.sources)),
                                colors,
                            )
                    ui.label("Health Check").classes("section-title mt-2")
                    health = engine.health()
                    with ui.row().classes("items-center gap-2"):
                        status_badge(health.get("status", "unknown"))
                        ui.label(f"Project: {health.get('project', '—')}").classes("text-sm").style(
                            f"color: {colors['text_muted']}"
                        )
                else:
                    ui.label("No engine configured — running in hub/HTTP mode.").style(
                        f"color: {colors['text_muted']}; font-size: 13px;"
                    )

                ui.separator()

                # ── UI preferences ───────────────────────────────────────
                ui.label("Studio Preferences").classes(_SECTION_HEADING).style(
                    f"color: {colors['text_primary']}"
                )
                with ui.card().classes("dex-card").style(_CARD_STYLE):
                    _prefs_form(config, colors, theme)

                if config is not None:
                    ui.separator()
                    ui.label("Connection").classes(_SECTION_HEADING).style(
                        f"color: {colors['text_primary']}"
                    )
                    with (
                        ui.card().classes("dex-card").style(_CARD_STYLE),
                        ui.grid(columns=2).classes("gap-x-8 gap-y-3"),
                    ):
                        _row("API URL", config.api_url, colors)
                        _row("Host", config.host, colors)
                        _row("Port", str(config.port), colors)


def _prefs_form(
    config: StudioConfig | None,
    colors: dict[str, str],
    theme: str,
) -> None:
    """Render the editable preferences form."""
    poll_val = config.poll_interval if config else 5.0

    with ui.column().classes("gap-4"):
        # Theme toggle
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-0"):
                ui.label("Theme").classes("text-sm font-medium").style(
                    f"color: {colors['text_primary']}"
                )
                ui.label("Reload page to apply.").style(
                    f"color: {colors['text_dim']}; font-size: 11px;"
                )
            toggle = ui.toggle(
                {"dark": "Dark", "light": "Light"},
                value=theme,
            ).props("dense")

        # Poll interval
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Poll interval (seconds)").classes("text-sm").style(
                f"color: {colors['text_primary']}"
            )
            poll_input = ui.number(value=poll_val, min=1, max=60, step=1, format="%.0f").style(
                "max-width: 80px;"
            )

        def _save_prefs() -> None:
            base = config or StudioConfig()
            from dataclasses import asdict

            updated = StudioConfig(
                **{
                    **asdict(base),
                    "theme": toggle.value,
                    "poll_interval": float(poll_input.value or poll_val),
                }
            )
            save_config(updated)
            ui.notify("Preferences saved. Reload to apply theme.", type="positive")

        ui.button("Save preferences", on_click=_save_prefs).style(
            f"background: {colors['accent']}; color: white; margin-top: 8px;"
        )


def _row(label: str, value: str, colors: dict[str, str]) -> None:
    """Render a label/value pair inside a settings grid."""
    ui.label(label).classes("text-sm").style(f"color: {colors['text_muted']}")
    ui.label(value).classes("text-sm font-mono").style(f"color: {colors['text_primary']}")
