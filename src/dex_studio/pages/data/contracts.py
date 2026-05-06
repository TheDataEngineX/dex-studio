from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell


def data_contracts() -> rx.Component:
    return page_shell(
        "Data Contracts",
        rx.callout.root(
            rx.callout.text("Data contracts are managed via dex.yaml — no API endpoint yet."),
            color="blue",
        ),
    )
