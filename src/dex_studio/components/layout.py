from __future__ import annotations

from typing import Any

import reflex as rx

from dex_studio.state.base import BaseState


class LayoutState(rx.State):
    sidebar_open: bool = False

    @rx.event
    def toggle_sidebar(self) -> None:
        self.sidebar_open = not self.sidebar_open

    @rx.event
    def close_sidebar(self) -> None:
        self.sidebar_open = False

    @staticmethod
    def is_project_loaded() -> bool:
        """Check if a project is loaded."""
        from dex_studio._engine import get_engine

        return get_engine() is not None


# ── Status helpers ───────────────────────────────────────────────────────────

_STATUS_COLORS: dict[str, str] = {
    "running": "blue",
    "success": "green",
    "failed": "red",
    "queued": "orange",
    "warning": "yellow",
    "stopped": "gray",
    "dev": "purple",
    "staging": "orange",
    "prod": "green",
    "info": "blue",
    "error": "red",
    "ok": "green",
    "active": "green",
    "inactive": "gray",
}

# ── Reusable metric card (exported for domain pages) ─────────────────────────


def metric_card(
    icon: str,
    label: str,
    value: rx.Var[Any],
    accent: str = "indigo",
    trend: str = "",
) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=17, color=f"var(--{accent}-9)"),
                    padding="8px",
                    background=f"var(--{accent}-3)",
                    border_radius="var(--radius-2)",
                    display="flex",
                    align_items="center",
                    justify_content="center",
                ),
                rx.spacer(),
                rx.cond(
                    trend != "",
                    rx.badge(trend, color_scheme="green", variant="soft", size="1"),
                    rx.fragment(),
                ),
                align="center",
                width="100%",
            ),
            rx.heading(value, size="6", weight="bold"),
            rx.text(label, size="2", color="var(--gray-9)"),
            spacing="2",
            align="start",
        ),
        padding="5",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="var(--radius-3)",
        _hover={
            "border_color": f"var(--{accent}-6)",
            "box_shadow": f"0 0 0 1px var(--{accent}-4), 0 2px 8px rgba(0,0,0,0.2)",
        },
        transition="all 0.15s ease",
    )


def status_badge(value: Any, color_map: dict[str, str] | None = None) -> rx.Component:
    colors = color_map or _STATUS_COLORS
    color = colors.get(str(value).lower(), "gray")
    return rx.badge(value, color_scheme=color, variant="soft")


# ── Nav definitions ──────────────────────────────────────────────────────────

_DOMAINS = [
    ("Data", "/data", "database", "indigo"),
    ("ML", "/ml", "brain", "violet"),
    ("AI", "/ai", "sparkles", "cyan"),
    ("System", "/system", "server", "orange"),
    ("Career", "/career", "briefcase", "teal"),
]

_SUBNAV: dict[str, list[tuple[str, str, str]]] = {
    "/data": [
        ("Overview", "/data", "layout-dashboard"),
        ("Pipelines", "/data/pipelines", "git-branch-plus"),
        ("Catalog", "/data/catalog", "book"),
        ("Sources", "/data/sources", "database"),
        ("SQL", "/data/sql", "terminal"),
        ("Quality", "/data/quality", "shield-check"),
        ("Lineage", "/data/lineage", "waypoints"),
    ],
    "/ml": [
        ("Overview", "/ml", "layout-dashboard"),
        ("Experiments", "/ml/experiments", "flask-conical"),
        ("Models", "/ml/models", "box"),
        ("Features", "/ml/features", "layers"),
        ("Predictions", "/ml/predictions", "target"),
        ("Drift", "/ml/drift", "activity"),
    ],
    "/ai": [
        ("Overview", "/ai", "layout-dashboard"),
        ("Agents", "/ai/agents", "bot"),
        ("Playground", "/ai/playground", "joystick"),
        ("Knowledge", "/ai/collections", "library"),
        ("Routing", "/ai/router", "route"),
        ("Traces", "/ai/traces", "waypoints"),
        ("Cost", "/ai/cost", "circle-dollar-sign"),
    ],
    "/system": [
        ("Status", "/system", "heart-pulse"),
        ("Metrics", "/system/metrics", "bar-chart-2"),
        ("Logs", "/system/logs", "scroll-text"),
        ("Components", "/system/components", "cpu"),
        ("Incidents", "/system/incidents", "siren"),
        ("Audit", "/system/activity", "history"),
        ("Settings", "/system/settings", "settings"),
    ],
    "/career": [
        ("CareerDEX", "/career", "external-link"),
    ],
}


def _domain_link(label: str, href: str, icon: str, accent: str) -> rx.Component:
    is_active = rx.State.router.page.path.startswith(href)
    return rx.link(
        rx.hstack(
            rx.box(
                rx.icon(
                    icon,
                    size=14,
                    color=rx.cond(is_active, f"var(--{accent}-9)", "var(--gray-9)"),
                ),
                width="28px",
                height="28px",
                border_radius="var(--radius-2)",
                background=rx.cond(is_active, f"var(--{accent}-3)", "transparent"),
                display="flex",
                align_items="center",
                justify_content="center",
                flex_shrink="0",
                transition="background 0.1s ease",
            ),
            rx.text(label, size="2", weight=rx.cond(is_active, "600", "400")),
            spacing="2",
            align="center",
        ),
        href=href,
        color=rx.cond(is_active, f"var(--{accent}-11)", "var(--gray-11)"),
        text_decoration="none",
        padding_x="3",
        padding_y="2",
        width="100%",
        display="flex",
        align_items="center",
        border_radius="var(--radius-2)",
        background=rx.cond(is_active, f"var(--{accent}-2)", "transparent"),
        _hover={"background": f"var(--{accent}-2)", "color": f"var(--{accent}-11)"},
        transition="all 0.12s ease",
    )


def _sub_link(label: str, href: str, icon: str) -> rx.Component:
    is_active = rx.State.router.page.path == href
    return rx.link(
        rx.hstack(
            rx.box(
                width="3px",
                height="14px",
                border_radius="2px",
                background=rx.cond(is_active, "var(--accent-9)", "transparent"),
                flex_shrink="0",
            ),
            rx.icon(icon, size=13),
            rx.text(label, size="1"),
            spacing="2",
            align="center",
        ),
        href=href,
        color=rx.cond(is_active, "var(--accent-11)", "var(--gray-10)"),
        font_weight=rx.cond(is_active, "600", "400"),
        text_decoration="none",
        padding_x="3",
        padding_y="1",
        padding_left="5",
        width="100%",
        display="flex",
        align_items="center",
        border_radius="var(--radius-2)",
        background=rx.cond(is_active, "var(--accent-2)", "transparent"),
        _hover={"background": "var(--accent-2)", "color": "var(--accent-11)"},
        transition="all 0.1s ease",
    )


def _subnav_section(prefix: str) -> rx.Component:
    items = _SUBNAV.get(prefix, [])
    if not items:
        return rx.fragment()
    is_active_domain = rx.State.router.page.path.startswith(prefix)
    return rx.cond(
        is_active_domain,
        rx.vstack(
            *[_sub_link(lbl, href, icon) for lbl, href, icon in items],
            spacing="0",
            width="100%",
            padding_y="1",
            border_left="1px solid var(--gray-4)",
            margin_left="5",
            margin_bottom="1",
        ),
        rx.fragment(),
    )


def sidebar() -> rx.Component:
    return rx.cond(
        LayoutState.is_project_loaded(),
        rx.box(
            rx.vstack(
                # Logo area
                rx.hstack(
                    rx.box(
                        rx.icon("zap", size=15, color="white"),
                        background="var(--indigo-9)",
                        padding="7px",
                        border_radius="var(--radius-2)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.heading("DEX Studio", size="3", weight="bold"),
                        rx.text("DataEngineX Platform", size="1", color="var(--gray-9)"),
                        spacing="0",
                        align="start",
                    ),
                    spacing="2",
                    align="center",
                    padding_x="3",
                    padding_top="4",
                    padding_bottom="3",
                    width="100%",
                ),
                rx.divider(margin_y="1"),
                *[
                    rx.vstack(
                        _domain_link(label, href, icon, accent),
                        _subnav_section(href),
                        spacing="0",
                        width="100%",
                    )
                    for label, href, icon, accent in _DOMAINS
                ],
                rx.spacer(),
                rx.divider(margin_y="2"),
                rx.hstack(
                    rx.link(
                        rx.hstack(
                            rx.icon("book-open", size=12),
                            rx.text("Docs", size="1"),
                            spacing="1",
                            align="center",
                        ),
                        href="https://docs.thedataenginex.org",
                        is_external=True,
                        color="var(--gray-9)",
                        text_decoration="none",
                        _hover={"color": "var(--gray-12)"},
                    ),
                    rx.spacer(),
                    rx.color_mode.button(size="1", variant="ghost"),
                    rx.link(
                        rx.icon("folder_git", size=13, color="var(--gray-9)"),
                        href="https://github.com/TheDataEngineX",
                        is_external=True,
                        _hover={"color": "var(--gray-12)"},
                    ),
                    padding_x="3",
                    padding_y="3",
                    align="center",
                    width="100%",
                ),
                align="start",
                spacing="0",
                height="100%",
                width="100%",
            ),
            class_name=rx.cond(
                LayoutState.sidebar_open,
                "dex-sidebar dex-sidebar-open",
                "dex-sidebar",
            ),
            position="fixed",
            left="0",
            top="0",
            height="100vh",
            width="220px",
            background="var(--gray-1)",
            border_right="1px solid var(--gray-4)",
            z_index="100",
            overflow_y="auto",
        ),
        rx.fragment(),  # No sidebar when no project loaded
    )


# ── Toast overlay ────────────────────────────────────────────────────────────


def _toast_item(toast: dict[str, str]) -> rx.Component:
    kind = toast.get("kind", "info")
    color = _STATUS_COLORS.get(kind, "blue")
    icon_name = {
        "error": "circle-x",
        "success": "circle-check",
        "warning": "triangle-alert",
    }.get(kind, "info")
    return rx.box(
        rx.hstack(
            rx.icon(icon_name, size=16, color=f"var(--{color}-9)"),
            rx.text(toast.get("message", ""), size="2", flex="1"),
            rx.icon_button(
                rx.icon("x", size=12),
                size="1",
                variant="ghost",
                aria_label="Dismiss notification",
                on_click=BaseState.clear_toasts,
            ),
            spacing="2",
            align="center",
        ),
        background="var(--gray-2)",
        border=f"1px solid var(--{color}-6)",
        border_radius="var(--radius-3)",
        padding="3",
        min_width="280px",
        max_width="400px",
        box_shadow="var(--shadow-3)",
    )


def toast_overlay() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.foreach(BaseState.toasts, _toast_item),
            spacing="2",
            align="end",
        ),
        position="fixed",
        bottom="4",
        right="4",
        z_index="9999",
    )


# ── Skeleton loaders ─────────────────────────────────────────────────────────


def skeleton_row(cols: int = 4) -> rx.Component:
    return rx.table.row(
        *[
            rx.table.cell(
                rx.box(
                    height="16px",
                    background="var(--gray-4)",
                    border_radius="var(--radius-1)",
                    animation="pulse 1.5s ease-in-out infinite",
                )
            )
            for _ in range(cols)
        ]
    )


def skeleton_table(rows: int = 5, cols: int = 4) -> rx.Component:
    return rx.table.root(
        rx.table.body(*[skeleton_row(cols) for _ in range(rows)]),
        width="100%",
    )


# ── Page shell ───────────────────────────────────────────────────────────────


def page_shell(
    title: str,
    *content: rx.Component,
    breadcrumb: list[tuple[str, str]] | None = None,
    **props: Any,
) -> rx.Component:
    crumbs: list[tuple[str, str]] = breadcrumb or []

    breadcrumb_bar = (
        rx.hstack(
            *[
                rx.hstack(
                    rx.link(rx.text(label, size="1", color="var(--gray-9)"), href=href),
                    rx.text("/", size="1", color="var(--gray-6)"),
                    spacing="1",
                )
                for label, href in crumbs
            ],
            rx.text(title, size="1", color="var(--gray-11)"),
            spacing="1",
            margin_bottom="2",
        )
        if crumbs
        else rx.fragment()
    )

    return rx.box(
        rx.link(
            "Skip to main content",
            href="#main-content",
            position="absolute",
            top="-100%",
            left="4px",
            z_index="9999",
            padding="2",
            background="var(--accent-9)",
            color="white",
            border_radius="var(--radius-2)",
            font_size="0.875rem",
            text_decoration="none",
            _focus={"top": "4px"},
            transition="top 0.1s",
        ),
        sidebar(),
        # Mobile header bar
        rx.box(
            rx.hstack(
                rx.icon_button(
                    rx.icon("menu", size=16),
                    size="2",
                    variant="ghost",
                    aria_label="Open navigation",
                    on_click=LayoutState.toggle_sidebar,
                ),
                rx.heading("DEX Studio", size="3", weight="bold"),
                rx.spacer(),
                spacing="3",
                align="center",
                width="100%",
            ),
            class_name="dex-mobile-header",
        ),
        rx.box(
            # Sticky page header
            rx.box(
                rx.hstack(
                    rx.vstack(
                        breadcrumb_bar,
                        rx.heading(title, size="5", weight="bold"),
                        spacing="1",
                        align="start",
                    ),
                    rx.spacer(),
                    align="center",
                    width="100%",
                ),
                padding_x="6",
                padding_y="4",
                border_bottom="1px solid var(--gray-4)",
                background="var(--gray-1)",
            ),
            # Content area
            rx.box(
                *content,
                id="main-content",
                padding="6",
                width="100%",
            ),
            class_name="dex-content",
            min_height="100vh",
            background="var(--gray-2)",
        ),
        toast_overlay(),
        **props,
    )


# ── Hub nav strip ─────────────────────────────────────────────────────────────


def hub_nav_strip(*items: tuple[str, str, str]) -> rx.Component:
    """Underline tab strip for intra-domain sub-grouping.

    Each item is (label, href, icon_name).
    """
    current_path = rx.State.router.page.path

    def _tab(label: str, href: str, icon: str) -> rx.Component:
        is_active = current_path == href
        return rx.link(
            rx.hstack(
                rx.icon(icon, size=13),
                rx.text(label, size="2"),
                spacing="1",
                align="center",
            ),
            href=href,
            class_name=rx.cond(is_active, "hub-nav-tab active", "hub-nav-tab"),
            text_decoration="none",
        )

    return rx.box(
        rx.hstack(*[_tab(lbl, href, icon) for lbl, href, icon in items], spacing="0"),
        class_name="hub-nav-strip",
    )


# ── Empty state ───────────────────────────────────────────────────────────────


def empty_state(
    icon: str,
    title: str,
    body: str = "",
) -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon(icon, size=40, color="var(--gray-7)"),
            rx.text(title, weight="medium", color="var(--gray-10)"),
            rx.cond(
                body != "",
                rx.text(body, size="2", color="var(--gray-8)"),
                rx.fragment(),
            ),
            align="center",
            spacing="2",
            padding_y="10",
        ),
    )
