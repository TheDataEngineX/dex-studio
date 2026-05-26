from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def email_checker_page() -> rx.Component:
    return page_shell(
        "Email Checker",
        rx.heading("Job Email Scanner", size="5", margin_bottom="4"),
        rx.vstack(
            rx.heading("Inbox Scanning", size="4"),
            rx.text(
                "Scan your email inbox for job-related messages "
                "and match them to tracked applications.",
            ),
            rx.callout.root(
                rx.vstack(
                    rx.text("Email Configuration Required", weight="bold"),
                    rx.text("Configure IMAP settings to scan your inbox:"),
                    rx.code("~/.dex-studio/careerdex/email.yaml", width="100%"),
                ),
                color_scheme="blue",
            ),
            rx.vstack(
                rx.text("Settings Format:", weight="bold"),
                rx.code(
                    """
imap_host: imap.gmail.com
imap_port: 993
email: your.email@gmail.com
password: app_password
             """.strip(),
                    width="100%",
                ),
                spacing="2",
            ),
            rx.callout.root(
                rx.callout.text("Use CLI to scan: dex career email --scan"),
                color_scheme="gray",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
