from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import LineageState


def _lineage_row(e: dict) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.text(e["source"], weight="bold", size="2"),
            rx.icon("arrow-right", size=14, color="gray"),
            rx.text(e["target"], weight="bold", size="2"),
            rx.spacer(),
            rx.text(e["timestamp"], size="1", color="gray"),
            align="center",
            width="100%",
        ),
        width="100%",
    )


def data_asset_graph() -> rx.Component:
    return page_shell(
        "Asset Graph",
        rx.callout.root(
            rx.callout.text(
                "Visual graph rendering requires a graph library. Showing source→target pairs."
            ),
            color="blue",
            margin_bottom="4",
        ),
        rx.cond(
            LineageState.error != "",
            rx.callout.root(rx.callout.text(LineageState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(LineageState.is_loading, rx.spinner(), rx.fragment()),
        rx.vstack(
            rx.foreach(LineageState.lineage_events, _lineage_row),
            width="100%",
            spacing="2",
        ),
        on_mount=LineageState.load_lineage,
    )
