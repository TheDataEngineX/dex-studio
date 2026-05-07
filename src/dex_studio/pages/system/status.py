from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.system import SystemState


def _health_banner() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.cond(
                SystemState.health["status"] == "ok",
                rx.icon("circle-check", size=20, color="var(--green-9)"),
                rx.icon("circle-alert", size=20, color="var(--red-9)"),
            ),
            rx.vstack(
                rx.text("Overall Health", size="1", color="var(--gray-9)", weight="medium"),
                rx.badge(
                    SystemState.health["status"],  # type: ignore[index]
                    color_scheme=rx.cond(SystemState.health["status"] == "ok", "green", "red"),
                    variant="soft",
                    size="2",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        padding="5",
        background="var(--gray-2)",
        border=rx.cond(
            SystemState.health["status"] == "ok",
            "1px solid var(--green-6)",
            "1px solid var(--red-6)",
        ),
        border_radius="var(--radius-3)",
    )


def _component_card(comp: dict) -> rx.Component:  # type: ignore[type-arg]
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    width="10px",
                    height="10px",
                    border_radius="50%",
                    background=rx.cond(
                        comp["status"] == "ok",  # type: ignore[index]
                        "var(--green-9)",
                        "var(--red-9)",
                    ),
                    flex_shrink="0",
                ),
                rx.text(comp["name"], weight="medium", size="2"),  # type: ignore[index]
                spacing="2",
                align="center",
            ),
            rx.badge(
                comp["status"],  # type: ignore[index]
                color_scheme=rx.cond(comp["status"] == "ok", "green", "red"),  # type: ignore[index]
                variant="soft",
                size="1",
            ),
            spacing="2",
            align="start",
        ),
        padding="4",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        _hover={"border_color": "var(--gray-6)"},
        transition="border-color 0.12s ease",
    )


def _skeleton_card() -> rx.Component:
    return rx.box(
        rx.box(
            height="60px",
            background="var(--gray-4)",
            border_radius="var(--radius-2)",
            animation="pulse 1.5s ease-in-out infinite",
        ),
        padding="4",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
    )


def system_status() -> rx.Component:
    return page_shell(
        "System Status",
        rx.cond(
            SystemState.error != "",
            rx.callout.root(
                rx.callout.text(SystemState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        rx.hstack(
            rx.cond(
                SystemState.is_loading,
                rx.spinner(size="2"),
                rx.fragment(),
            ),
            rx.button(
                rx.icon("refresh-cw", size=14),
                "Refresh",
                variant="outline",
                size="2",
                on_click=[SystemState.load_health, SystemState.load_components],
            ),
            rx.cond(
                SystemState.last_refreshed != "",
                rx.text(
                    "Auto-refreshed: ",
                    SystemState.last_refreshed,
                    size="1",
                    color="var(--gray-9)",
                ),
                rx.fragment(),
            ),
            spacing="3",
            align="center",
            margin_bottom="5",
        ),
        rx.grid(
            _health_banner(),
            columns="4",
            gap="4",
            margin_bottom="5",
        ),
        rx.heading(
            "Components",
            size="3",
            weight="medium",
            color="var(--gray-12)",
            margin_bottom="3",
        ),
        rx.cond(
            SystemState.is_loading,
            rx.grid(
                *[_skeleton_card() for _ in range(8)],
                columns="4",
                gap="3",
            ),
            rx.grid(
                rx.foreach(SystemState.components_list, _component_card),
                columns="4",
                gap="3",
            ),
        ),
        on_mount=[
            SystemState.load_health,
            SystemState.load_components,
            SystemState.start_auto_refresh,
        ],
    )
