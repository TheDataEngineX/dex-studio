from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell


def data_templates() -> rx.Component:
    return page_shell(
        "Pipeline Templates",
        rx.callout.root(
            rx.callout.text("Pipeline templates are managed via dex.yaml — no API endpoint yet."),
            color="blue",
        ),
    )
