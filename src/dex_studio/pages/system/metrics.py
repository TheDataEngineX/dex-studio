from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import metric_card, page_shell
from dex_studio.state.system import SystemState


def _metric_card(entry: list) -> rx.Component:
    return metric_card("activity", entry[0], entry[1], accent="orange")


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
