"""Settings page — connection config and preferences.

Route: ``/settings``

Allows the user to view/edit the DEX engine URL, auth token,
and UI preferences.  Changes are persisted to the Studio config
file at ``~/.dex-studio/config.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from nicegui import app, ui

from dex_studio.client import DexClient
from dex_studio.components import page_layout
from dex_studio.config import StudioConfig, load_config
from dex_studio.theme import COLORS

_CONFIG_PATH = Path.home() / ".dex-studio" / "config.yaml"


@ui.page("/settings")
async def settings_page() -> None:
    """Render the settings page."""
    with page_layout("Settings", active_route="/settings") as _content:
        cfg: StudioConfig = app.storage.general.get("config") or load_config()

        ui.label("Connection").classes("section-title")
        with ui.card().classes("dex-card w-full"):
            api_url = (
                ui.input(
                    label="DEX Engine URL",
                    value=cfg.api_url,
                )
                .classes("w-96")
                .props("outlined dark")
            )

            api_token = (
                ui.input(
                    label="API Token (optional)",
                    value=cfg.api_token or "",
                    password=True,
                    password_toggle_button=True,
                )
                .classes("w-96")
                .props("outlined dark")
            )

            timeout = (
                ui.number(
                    label="Timeout (seconds)",
                    value=cfg.timeout,
                    min=1,
                    max=120,
                )
                .classes("w-48")
                .props("outlined dark")
            )

        ui.label("UI Preferences").classes("section-title mt-6")
        with ui.card().classes("dex-card w-full"):
            theme = ui.toggle(
                options=["dark", "light"],
                value=cfg.theme,
            ).classes("mt-1")

            poll = (
                ui.number(
                    label="Status poll interval (seconds)",
                    value=cfg.poll_interval,
                    min=1,
                    max=60,
                )
                .classes("w-48")
                .props("outlined dark")
            )

        # -- Actions --
        status_label = ui.label("").classes("text-sm mt-2")

        async def test_connection() -> None:
            status_label.set_text("Testing…")
            status_label.style(f"color: {COLORS['text_muted']}")

            test_cfg = StudioConfig(
                api_url=api_url.value or cfg.api_url,
                api_token=api_token.value or None,
                timeout=float(timeout.value or cfg.timeout),
            )
            test_client = DexClient(config=test_cfg)
            try:
                await test_client.connect()
                ok = await test_client.ping()
                if ok:
                    status_label.set_text("Connection successful ✓")
                    status_label.style(f"color: {COLORS['success']}")
                else:
                    status_label.set_text("Connection failed — engine not reachable")
                    status_label.style(f"color: {COLORS['error']}")
            except Exception as exc:
                status_label.set_text(f"Error: {exc}")
                status_label.style(f"color: {COLORS['error']}")
            finally:
                await test_client.close()

        def save_config() -> None:
            data: dict[str, Any] = {
                "api_url": api_url.value,
                "timeout": float(timeout.value or cfg.timeout),
                "theme": theme.value,
                "poll_interval": float(poll.value or cfg.poll_interval),
            }
            token = api_token.value
            if token:
                data["api_token"] = token

            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _CONFIG_PATH.open("w") as fh:
                yaml.safe_dump(data, fh, default_flow_style=False)

            status_label.set_text(f"Saved to {_CONFIG_PATH}")
            status_label.style(f"color: {COLORS['success']}")

        with ui.row().classes("gap-3 mt-4"):
            ui.button(
                "Test Connection",
                icon="lan",
                on_click=test_connection,
            ).props("flat color=indigo")
            ui.button(
                "Save",
                icon="save",
                on_click=save_config,
            ).props("color=indigo")

        # -- Current config display --
        ui.label("Current Config File").classes("section-title mt-6")
        if _CONFIG_PATH.exists():
            with ui.card().classes("dex-card w-full"):
                raw = _CONFIG_PATH.read_text()
                ui.code(raw, language="yaml").classes("w-full")
        else:
            ui.label(f"No config file at {_CONFIG_PATH}").style(f"color: {COLORS['text_muted']}")
