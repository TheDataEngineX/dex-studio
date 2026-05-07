from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell


def _strategy_card(name: str, description: str) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(name, size="3", weight="bold"),
            rx.text(description, size="2", color_scheme="gray"),
            spacing="1",
        ),
        padding="4",
    )


def ai_router() -> rx.Component:
    return page_shell(
        "Model Router",
        rx.heading("AI Router", size="5", margin_bottom="4"),
        rx.callout.root(
            rx.callout.text(
                "Router rules are configured in dex.yaml — edit your config to update routing strategy."
            ),
            color_scheme="indigo",
            margin_bottom="6",
        ),
        rx.heading("Routing Strategies", size="4", margin_bottom="3"),
        rx.vstack(
            _strategy_card(
                "complexity",
                "Routes to a cheaper/faster model for simple tasks and a more capable model for complex tasks.",
            ),
            _strategy_card(
                "round_robin",
                "Distributes requests evenly across all configured providers.",
            ),
            _strategy_card(
                "fallback",
                "Tries providers in order; falls back to the next if the primary fails.",
            ),
            _strategy_card(
                "cost",
                "Always routes to the lowest-cost provider that can handle the request.",
            ),
            spacing="3",
            max_width="600px",
        ),
    )
