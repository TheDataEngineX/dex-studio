from __future__ import annotations

import time

import reflex as rx

from dex_studio.components.layout import page_shell


class ConnectionState(rx.State):
    latency_ms: float = 0.0
    api_version: str = ""
    status: str = ""
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def ping(self) -> None:
        self.is_loading = True
        self.error = ""
        self.status = ""
        yield
        start = time.monotonic()
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None:
                self.status = "no config"
                self.error = "DEX_CONFIG_PATH not set — engine not initialized"
                return
            data = eng.health()
            self.latency_ms = round((time.monotonic() - start) * 1000, 1)
            self.api_version = data.get("project", "unknown")
            self.status = data.get("status", "unknown")
        except Exception as exc:
            self.error = str(exc)
            self.status = "error"
        finally:
            self.is_loading = False


def system_connection() -> rx.Component:
    return page_shell(
        "Connection",
        rx.heading("API Connection", size="5", margin_bottom="4"),
        rx.cond(
            ConnectionState.error != "",
            rx.callout.root(
                rx.callout.text(ConnectionState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.text("Config:", size="2", weight="bold"),
                    rx.code(ConnectionState.api_version),
                    spacing="2",
                    align_items="center",
                ),
                rx.button(
                    rx.cond(ConnectionState.is_loading, rx.spinner(), rx.text("Test Connection")),
                    on_click=ConnectionState.ping,
                    color_scheme="indigo",
                    disabled=ConnectionState.is_loading,
                ),
                rx.cond(
                    ConnectionState.status != "",
                    rx.hstack(
                        rx.text("Status:", size="2", weight="bold"),
                        rx.badge(
                            ConnectionState.status,
                            color_scheme=rx.cond(
                                ConnectionState.status == "online", "green", "red"
                            ),
                        ),
                        rx.text("Latency:", size="2", weight="bold"),
                        rx.text(ConnectionState.latency_ms, size="2"),
                        rx.text("ms", size="2"),
                        rx.text("Version:", size="2", weight="bold"),
                        rx.text(ConnectionState.api_version, size="2"),
                        spacing="2",
                        align_items="center",
                        flex_wrap="wrap",
                    ),
                    rx.fragment(),
                ),
                spacing="4",
            ),
            max_width="560px",
        ),
    )
