from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell


def ml_ab_test() -> rx.Component:
    return page_shell(
        "A/B Tests",
        rx.callout.root(
            rx.callout.text("A/B tests — no API endpoint yet."),
            color="blue",
        ),
    )
