from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def pdf_export_page() -> rx.Component:
    return page_shell(
        "PDF Export",
        rx.callout.root(
            rx.callout.text("ATS-optimized PDF resume export. Requires careerdex[pdf] extra."),
            color_scheme="blue",
        ),
        on_mount=CareerState.load_applications,
    )
