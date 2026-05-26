from __future__ import annotations

from typing import Any

import reflex as rx

from careerdex.state.career import CareerState

_S_OVERVIEW = "Overview"
_S_SEARCH = "Job Search"
_S_PREPARE = "Prepare"
_S_PREP = "Prep"
_S_NETWORK = "Network"

NAV_LINKS: list[tuple[str, str, str, str]] = [
    # Overview
    ("Dashboard", "/", "layout-dashboard", _S_OVERVIEW),
    ("Analytics", "/analytics", "bar-chart-2", _S_OVERVIEW),
    # Job Search
    ("Discover", "/discover", "search", _S_SEARCH),
    ("Jobs", "/jobs", "briefcase", _S_SEARCH),
    ("Applications", "/applications", "kanban", _S_SEARCH),
    ("Pipeline", "/pipeline", "file-input", _S_SEARCH),
    ("Scanner", "/scanner", "scan-line", _S_SEARCH),
    # Prepare
    ("Profile", "/profile", "user", _S_PREPARE),
    ("Resume", "/resume", "file-text", _S_PREPARE),
    ("Matcher", "/resume-matcher", "shuffle", _S_PREPARE),
    ("Cover Letter", "/cover-letter", "mail", _S_PREPARE),
    ("PDF Export", "/pdf-export", "download", _S_PREPARE),
    # Prep
    ("Interview", "/interview", "message-square", _S_PREP),
    ("Stories", "/stories", "book-open", _S_PREP),
    ("Evaluate", "/evaluate", "clipboard-check", _S_PREP),
    ("Research", "/research", "telescope", _S_PREP),
    ("Negotiate", "/negotiate", "handshake", _S_PREP),
    ("Prep Hub", "/prep", "graduation-cap", _S_PREP),
    # Network
    ("Networking", "/networking", "users", _S_NETWORK),
    ("Progress", "/progress", "trending-up", _S_NETWORK),
    ("Courses", "/courses", "book", _S_NETWORK),
    ("Projects", "/projects", "folder-open", _S_NETWORK),
    ("Network", "/network", "link-2", _S_NETWORK),
]

_SECTIONS = [_S_OVERVIEW, _S_SEARCH, _S_PREPARE, _S_PREP, _S_NETWORK]

_STATUS_COLORS: dict[str, str] = {
    "offer": "green",
    "interview": "blue",
    "applied": "indigo",
    "rejected": "red",
    "saved": "gray",
}


def status_badge(value: Any, color_map: dict[str, str] | None = None) -> rx.Component:
    colors = color_map or _STATUS_COLORS
    color = colors.get(str(value).lower(), "gray")
    return rx.badge(value, color_scheme=color, variant="soft")  # type: ignore[no-any-return]


def _nav_link(label: str, href: str, icon: str) -> rx.Component:
    is_active = rx.State.router.page.path == href  # type: ignore[attr-defined]
    return rx.link(  # type: ignore[no-any-return]
        rx.hstack(
            rx.icon(
                icon,
                size=14,
                color=rx.cond(is_active, "var(--blue-9)", "var(--gray-10)"),
            ),
            rx.text(label, size="2"),
            spacing="2",
            align="center",
        ),
        href=href,
        color=rx.cond(is_active, "var(--blue-11)", "var(--gray-12)"),
        font_weight=rx.cond(is_active, "500", "400"),
        text_decoration="none",
        padding_x="3",
        padding_y="2",
        width="100%",
        display="flex",
        align_items="center",
        border_radius="var(--radius-2)",
        background=rx.cond(is_active, "var(--blue-3)", "transparent"),
        _hover={"background": "var(--blue-2)", "color": "var(--blue-11)"},
        transition="all 0.1s ease",
    )


def _section_label(label: str) -> rx.Component:
    return rx.text(  # type: ignore[no-any-return]
        label.upper(),
        size="1",
        weight="bold",
        color="var(--gray-9)",
        letter_spacing="0.07em",
        padding_x="3",
        padding_top="4",
        padding_bottom="1",
    )


def sidebar() -> rx.Component:
    sections: list[rx.Component] = []
    for section in _SECTIONS:
        items = [(lbl, h, ic) for lbl, h, ic, s in NAV_LINKS if s == section]
        if not items:
            continue
        sections.append(_section_label(section))
        for lbl, h, ic in items:
            sections.append(_nav_link(lbl, h, ic))

    return rx.box(  # type: ignore[no-any-return]
        rx.vstack(
            rx.divider(margin_y="1"),
            *sections,
            rx.spacer(),
            rx.divider(margin_y="2"),
            rx.hstack(
                rx.box(
                    width="8px",
                    height="8px",
                    border_radius="50%",
                    background="var(--green-9)",
                    flex_shrink="0",
                ),
                rx.text(
                    CareerState.applications_count,
                    " active",
                    size="1",
                    color="var(--gray-11)",
                    weight="medium",
                ),
                rx.text("applications", size="1", color="var(--gray-9)"),
                spacing="2",
                padding_x="3",
                padding_y="3",
                align="center",
            ),
            align="start",
            spacing="0",
            height="100%",
            width="100%",
            overflow_y="auto",
        ),
        position="fixed",
        left="0",
        top="64px",
        height="calc(100vh - 64px)",
        width="240px",
        background="white",
        border_right="1px solid var(--gray-4)",
        z_index="100",
    )


def top_navbar() -> rx.Component:
    return rx.box(  # type: ignore[no-any-return]
        rx.hstack(
            # Logo
            rx.link(
                rx.hstack(
                    rx.box(
                        rx.icon("briefcase", size=16, color="white"),
                        background="var(--blue-9)",
                        padding="7px",
                        border_radius="var(--radius-2)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.heading(
                        "CareerDEX",
                        size="3",
                        weight="bold",
                        color="var(--gray-12)",
                    ),
                    spacing="2",
                    align="center",
                ),
                href="/",
                text_decoration="none",
                color="inherit",
                flex_shrink="0",
                width="220px",
            ),
            # Search bar
            rx.box(
                rx.hstack(
                    rx.icon("search", size=15, color="var(--gray-9)"),
                    rx.el.input(
                        placeholder="Search jobs, companies, skills...",
                        style={
                            "background": "transparent",
                            "border": "none",
                            "outline": "none",
                            "fontSize": "14px",
                            "color": "var(--gray-12)",
                            "width": "100%",
                            "fontFamily": "inherit",
                        },
                    ),
                    spacing="2",
                    align="center",
                    padding_x="4",
                    background="var(--gray-3)",
                    border_radius="20px",
                    height="38px",
                    width="400px",
                    border="1.5px solid transparent",
                    _hover={"border_color": "var(--blue-5)"},
                    _focus_within={
                        "border_color": "var(--blue-7)",
                        "background": "white",
                        "box_shadow": "0 0 0 3px var(--blue-3)",
                    },
                    transition="all 0.15s ease",
                ),
                flex="1",
                display="flex",
                justify_content="center",
            ),
            # Right actions
            rx.hstack(
                rx.link(
                    rx.button(
                        "Find Jobs",
                        size="2",
                        color_scheme="blue",
                        variant="soft",
                        border_radius="20px",
                    ),
                    href="/discover",
                    text_decoration="none",
                ),
                rx.icon_button(
                    rx.icon("bell", size=15),
                    variant="ghost",
                    size="2",
                    color_scheme="gray",
                ),
                rx.avatar(
                    fallback="JD",
                    size="2",
                    color_scheme="blue",
                    cursor="pointer",
                    radius="full",
                ),
                spacing="3",
                align="center",
                flex_shrink="0",
                width="220px",
                justify="end",
            ),
            justify="between",
            align="center",
            padding_x="5",
            height="100%",
        ),
        position="fixed",
        top="0",
        left="0",
        right="0",
        height="64px",
        background="white",
        border_bottom="1px solid var(--gray-4)",
        z_index="200",
        box_shadow="0 1px 4px rgba(0,0,0,0.06)",
    )


def skeleton_row(cols: int = 4) -> rx.Component:
    return rx.table.row(  # type: ignore[no-any-return]
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
    return rx.table.root(  # type: ignore[no-any-return]
        rx.table.body(*[skeleton_row(cols) for _ in range(rows)]),
        width="100%",
    )


def skeleton_card() -> rx.Component:
    return rx.card(  # type: ignore[no-any-return]
        rx.hstack(
            rx.box(
                width="48px",
                height="48px",
                border_radius="var(--radius-3)",
                background="var(--gray-4)",
                animation="pulse 1.5s ease-in-out infinite",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.box(
                    height="18px",
                    width="55%",
                    background="var(--gray-4)",
                    border_radius="4px",
                    animation="pulse 1.5s ease-in-out infinite",
                ),
                rx.box(
                    height="14px",
                    width="35%",
                    background="var(--gray-3)",
                    border_radius="4px",
                    animation="pulse 1.5s ease-in-out infinite",
                ),
                spacing="2",
                flex="1",
            ),
            spacing="4",
            align="start",
        ),
        padding="4",
        background="white",
        border="1px solid var(--gray-4)",
        width="100%",
    )


def page_shell(
    title: str,
    *content: rx.Component,
    breadcrumb: list[tuple[str, str]] | None = None,
    **props: Any,
) -> rx.Component:
    crumbs = breadcrumb or []
    breadcrumb_bar = (
        rx.hstack(
            *[
                rx.hstack(
                    rx.link(rx.text(lbl, size="1", color="var(--gray-9)"), href=href),
                    rx.text("/", size="1", color="var(--gray-6)"),
                    spacing="1",
                )
                for lbl, href in crumbs
            ],
            rx.text(title, size="1", color="var(--gray-11)"),
            spacing="1",
            margin_bottom="3",
        )
        if crumbs
        else rx.fragment()
    )

    return rx.box(  # type: ignore[no-any-return]
        rx.link(
            "Skip to main content",
            href="#main-content",
            position="absolute",
            top="-100%",
            left="4px",
            z_index="9999",
            padding="2",
            background="var(--blue-9)",
            color="white",
            border_radius="var(--radius-2)",
            font_size="0.875rem",
            text_decoration="none",
            _focus={"top": "4px"},
            transition="top 0.1s",
        ),
        top_navbar(),
        sidebar(),
        rx.box(
            breadcrumb_bar,
            rx.heading(
                title,
                size="5",
                weight="bold",
                color="var(--gray-12)",
                margin_bottom="5",
            ),
            *content,
            id="main-content",
            margin_left="240px",
            padding_top="calc(64px + 24px)",
            padding_x="6",
            padding_bottom="8",
            width="100%",
            min_height="100vh",
            background="var(--gray-2)",
        ),
        **props,
    )
