from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.config import load_config, save_config


class SettingsState(rx.State):
    saved: bool = False
    error: str = ""

    @rx.event
    async def load_settings(self) -> None:
        try:
            load_config()
        except Exception as exc:
            self.error = str(exc)

    @rx.event
    async def save_settings(self) -> None:
        self.error = ""
        self.saved = False
        try:
            cfg = load_config()
            save_config(cfg)
            self.saved = True
        except Exception as exc:
            self.error = str(exc)


def system_settings() -> rx.Component:
    return page_shell(
        "Settings",
        rx.cond(
            SettingsState.error != "",
            rx.callout.root(
                rx.callout.text(SettingsState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.cond(
            SettingsState.saved,
            rx.callout.root(
                rx.callout.text("Settings saved."), color_scheme="green", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.card(
            rx.vstack(
                rx.heading("Appearance", size="3", weight="bold"),
                rx.hstack(
                    rx.text("Color mode", size="2"),
                    rx.spacer(),
                    rx.color_mode.button(size="2", variant="soft"),
                    align="center",
                    width="100%",
                ),
                rx.divider(margin_y="3"),
                rx.heading("About", size="3", weight="bold"),
                rx.text(
                    "DEX Studio — DataEngineX Platform UI",
                    size="2",
                    color="var(--gray-9)",
                ),
                spacing="3",
                align="start",
            ),
            max_width="480px",
            padding="5",
        ),
        on_mount=SettingsState.load_settings,
    )
