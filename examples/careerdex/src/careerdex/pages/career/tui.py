from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def tui_page() -> rx.Component:
    return page_shell(
        "Terminal UI",
        rx.vstack(
            rx.heading("Terminal Dashboard", size="5", margin_bottom="4"),
            rx.code(
                """
╔══════════════════════════════════════╗
║        CareerDEX TUI               ║
╠══════════════════════════════════════╣
║  Applications: {CareerState.applications_count}         ║
║  Interviews:  {CareerState.interviews_count}         ║
║  Offers:      {CareerState.offers_count}        ║
║  Response:    {CareerState.response_rate}      ║
╚══════════════════════════════════════╝
            """.strip()
            ),
            rx.text("Run CLI for terminal view:", weight="bold"),
            rx.code("dex career dashboard"),
            rx.link(
                rx.button("Open CLI Dashboard"),
                href="/",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
