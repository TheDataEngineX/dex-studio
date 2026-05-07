from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.system import SystemState


def _metric_card(entry: list) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(entry[0], size="2", color_scheme="gray"),
            rx.heading(rx.text(entry[1]), size="5"),
            spacing="1",
        ),
        padding="4",
        min_width="160px",
    )


def system_metrics() -> rx.Component:
    return page_shell(
        "Metrics",
        rx.heading("System Metrics", size="5", margin_bottom="4"),
        rx.cond(SystemState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            SystemState.error != "",
            rx.callout.root(
                rx.callout.text(SystemState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.cond(
            SystemState.metrics == {},
            rx.callout.root(
                rx.callout.text("No metrics available. DEX API may be offline."),
                color_scheme="gray",
            ),
            rx.flex(
                rx.foreach(
                    SystemState.metrics.items(),
                    _metric_card,
                ),
                wrap="wrap",
                gap="4",
            ),
        ),
        on_mount=SystemState.load_metrics,
    )
