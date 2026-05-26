from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _portal_row(company: dict) -> rx.Component:
    ats_colors = {
        "greenhouse": "green",
        "ashby": "blue",
        "lever": "orange",
        "workday": "purple",
        "custom": "gray",
    }
    ats = company.get("ats_platform", "custom")
    ats_color = ats_colors.get(ats, "gray")
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.box(
                    width="8px",
                    height="8px",
                    border_radius="50%",
                    background=rx.cond(
                        company.get("is_active", False), "var(--green-9)", "var(--gray-6)"
                    ),
                ),
                rx.text(company.get("name", ""), weight="medium"),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(company.get("industry", "")),
        rx.table.cell(rx.badge(ats, color_scheme=ats_color, variant="soft", size="1")),
        rx.table.cell(
            rx.text(
                company.get("careers_url", ""),
                size="1",
                color="var(--blue-10)",
                overflow="hidden",
                max_width="200px",
                text_overflow="ellipsis",
            )
        ),
    )


def scanner_page() -> rx.Component:
    return page_shell(
        "Portal Scanner",
        rx.vstack(
            rx.hstack(
                rx.icon("radar", size=18, color="var(--blue-9)"),
                rx.heading("45+ Company Portal Scanner", size="5"),
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    "Scan All",
                    color_scheme="blue",
                    on_click=lambda: CareerState.scan_portals(),
                ),
                align="center",
            ),
            rx.text(
                "Pre-configured scanners for Greenhouse, Ashby, Lever, "
                "Wellfound, and custom portals. Scan results cached in your local database.",
                size="2",
                color="var(--gray-9)",
                margin_bottom="4",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("AI Companies", size="4"),
                    rx.text(
                        "OpenAI, Anthropic, Mistral, Cohere, LangChain, Pinecone, "
                        "Google DeepMind, Meta AI, xAI",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                ),
                rx.divider(),
                rx.vstack(
                    rx.heading("Voice AI", size="4"),
                    rx.text(
                        "ElevenLabs, PolyAI, Parloa, Hume AI, Deepgram, Vapi, Bland AI",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                ),
                rx.divider(),
                rx.vstack(
                    rx.heading("AI Platforms", size="4"),
                    rx.text(
                        "Retool, Airtable, Vercel, Temporal, Glean, Arize AI",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                ),
                rx.divider(),
                rx.vstack(
                    rx.heading("Contact Center", size="4"),
                    rx.text(
                        "Ada, LivePerson, Sierra, Decagon, Talkdesk, Genesys",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                ),
                padding="4",
            ),
            rx.cond(
                CareerState.is_loading,
                rx.center(rx.spinner(), padding_y="6"),
            ),
            rx.cond(
                CareerState.error != "",
                rx.callout.root(rx.callout.text(CareerState.error), color_scheme="red"),
            ),
            rx.cond(
                CareerState.scan_results.length() > 0,
                rx.card(
                    rx.heading(f"Scan Results ({CareerState.scan_results.length()})", size="4"),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Company"),
                                rx.table.column_header_cell("Industry"),
                                rx.table.column_header_cell("ATS"),
                                rx.table.column_header_cell("Careers URL"),
                            )
                        ),
                        rx.table.body(rx.foreach(CareerState.scan_results, _portal_row)),
                    ),
                    padding="4",
                ),
            ),
            rx.card(
                rx.vstack(
                    rx.heading("Supported ATS Platforms", size="4"),
                    rx.flex(
                        rx.badge("Greenhouse", color_scheme="green", variant="soft"),
                        rx.badge("Ashby", color_scheme="blue", variant="soft"),
                        rx.badge("Lever", color_scheme="orange", variant="soft"),
                        rx.badge("Workday", color_scheme="purple", variant="soft"),
                        rx.badge("Wellfound", color_scheme="pink", variant="soft"),
                        rx.badge("Custom", color_scheme="gray", variant="soft"),
                        gap="2",
                        flex_wrap="wrap",
                    ),
                    spacing="3",
                ),
                padding="4",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_jobs,
    )
