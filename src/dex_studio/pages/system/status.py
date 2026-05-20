from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import empty_state, page_shell, section_heading
from dex_studio.state.system import SystemState


def _health_banner() -> rx.Component:
    is_ok = SystemState.health["status"] == "ok"  # type: ignore[index]
    return rx.box(
        rx.hstack(
            rx.box(
                rx.cond(
                    is_ok,
                    rx.icon("shield-check", size=24, color="var(--green-11)"),
                    rx.icon("shield-alert", size=24, color="var(--red-11)"),
                ),
                width="48px",
                height="48px",
                border_radius="var(--radius-3)",
                background=rx.cond(is_ok, "var(--green-3)", "var(--red-3)"),
                border=rx.cond(is_ok, "1px solid var(--green-6)", "1px solid var(--red-6)"),
                display="flex",
                align_items="center",
                justify_content="center",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text("Overall Health", size="1", color="var(--gray-9)", weight="medium"),
                rx.hstack(
                    rx.badge(
                        SystemState.health["status"],  # type: ignore[index]
                        color_scheme=rx.cond(is_ok, "green", "red"),
                        variant="soft",
                        size="2",
                        radius="full",
                    ),
                    rx.cond(
                        SystemState.last_refreshed != "",
                        rx.text(
                            "Updated: ",
                            SystemState.last_refreshed,
                            size="1",
                            color="var(--gray-8)",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text(
                    SystemState.components_list.length(),  # type: ignore[attr-defined]
                    size="5",
                    weight="bold",
                    color=rx.cond(is_ok, "var(--green-11)", "var(--red-11)"),
                ),
                rx.text("components", size="1", color="var(--gray-9)"),
                spacing="0",
                align="center",
            ),
            spacing="4",
            align="center",
            width="100%",
        ),
        padding="5",
        background=rx.cond(is_ok, "var(--green-2)", "var(--red-2)"),
        border=rx.cond(is_ok, "1px solid var(--green-5)", "1px solid var(--red-5)"),
        border_radius="var(--radius-3)",
        margin_bottom="6",
    )


def _component_card(comp: dict) -> rx.Component:  # type: ignore[type-arg]
    is_ok = comp["status"] == "ok"  # type: ignore[index]
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    class_name=rx.cond(is_ok, "status-dot ok", "status-dot error"),
                ),
                rx.text(comp["name"], weight="medium", size="2"),  # type: ignore[index]
                rx.spacer(),
                rx.badge(
                    comp["status"],  # type: ignore[index]
                    color_scheme=rx.cond(is_ok, "green", "red"),
                    variant="soft",
                    size="1",
                    radius="full",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                comp.get("message", "") != "",  # type: ignore[union-attr]
                rx.text(comp["message"], size="1", color="var(--gray-8)"),  # type: ignore[index]
                rx.fragment(),
            ),
            spacing="2",
            align="start",
        ),
        padding="4",
        background="var(--gray-2)",
        border=rx.cond(is_ok, "1px solid var(--gray-4)", "1px solid var(--red-5)"),
        border_radius="var(--radius-3)",
        _hover={"border_color": rx.cond(is_ok, "var(--green-5)", "var(--red-7)")},
        transition="border-color 0.12s ease",
    )


def _skeleton_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.box(
                height="12px",
                width="60%",
                background="var(--gray-4)",
                border_radius="var(--radius-1)",
                animation="pulse 1.5s ease-in-out infinite",
            ),
            rx.box(
                height="10px",
                width="40%",
                background="var(--gray-3)",
                border_radius="var(--radius-1)",
                animation="pulse 1.5s ease-in-out infinite",
            ),
            spacing="2",
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
        # Health banner — full width
        _health_banner(),
        # Components grid
        section_heading(
            "Components",
            subtitle="Live health status of all registered services.",
        ),
        rx.cond(
            SystemState.is_loading,
            rx.grid(
                *[_skeleton_card() for _ in range(8)],
                columns="4",
                gap="3",
            ),
            rx.cond(
                SystemState.components_list.length() == 0,  # type: ignore[attr-defined]
                empty_state(
                    "cpu",
                    "No components registered",
                    "Start the DEX server to see component health.",
                ),
                rx.grid(
                    rx.foreach(SystemState.components_list, _component_card),
                    columns="4",
                    gap="3",
                ),
            ),
        ),
        actions=rx.hstack(
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
            spacing="2",
            align="center",
        ),
        on_mount=[
            SystemState.load_health,
            SystemState.load_components,
            SystemState.start_auto_refresh,
        ],
    )
