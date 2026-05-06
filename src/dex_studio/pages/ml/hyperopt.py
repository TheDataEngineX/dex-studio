from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell


def ml_hyperopt() -> rx.Component:
    return page_shell(
        "Hyperparameter Optimization",
        rx.callout.root(
            rx.callout.text("Hyperopt runs — no API endpoint yet."),
            color="blue",
        ),
    )
