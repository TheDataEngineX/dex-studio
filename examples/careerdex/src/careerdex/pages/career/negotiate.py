from __future__ import annotations

import reflex as rx

from careerdex.components.layout import page_shell
from careerdex.state.career import CareerState


def _negotiation_card(title: str, description: str, icon: str, tips: list[str]) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.icon(icon, size=20, color="var(--green-9)"),
            rx.vstack(
                rx.text(title, size="3", weight="bold"),
                rx.text(description, size="2", color="var(--gray-10)"),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        rx.divider(),
        rx.vstack(
            rx.text("Key Talking Points", size="2", weight="bold", color="var(--gray-12)"),
            *[
                rx.hstack(
                    rx.box(
                        width="6px", height="6px", border_radius="50%", background="var(--green-9)"
                    ),
                    rx.text(tip, size="2", color="var(--gray-11)"),
                    spacing="2",
                    align="center",
                )
                for tip in tips
            ],
            spacing="2",
            align="start",
        ),
        padding="4",
        border="1px solid var(--green-4)",
        _hover={"border_color": "var(--green-7)"},
        transition="all 0.15s ease",
    )


def negotiate_page() -> rx.Component:
    return page_shell(
        "Negotiation",
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Negotiation Scripts & Frameworks", size="5", weight="bold"),
                    rx.text(
                        "Salary, equity, geographic discount pushback, "
                        "and competing offer leverage. Never leave money on the table.",
                        size="2",
                        color="var(--gray-9)",
                    ),
                    align="start",
                ),
                rx.spacer(),
                rx.badge("Career-Ops Method", color_scheme="green", variant="soft"),
                align="center",
            ),
            rx.card(
                rx.hstack(
                    rx.icon("alert-circle", size=16, color="var(--yellow-10)"),
                    rx.text(
                        "Always ask for time before responding to offers. "
                        "A 24-48 hour delay signals thoughtfulness, not desperation. "
                        "Use competing offers as leverage.",
                        size="2",
                        color="var(--gray-10)",
                    ),
                    spacing="2",
                    align="center",
                ),
                background="var(--yellow-2)",
                padding="3",
            ),
            rx.heading("Salary Negotiation", size="4", margin_top="4"),
            rx.grid(
                _negotiation_card(
                    "Base Salary",
                    "Don't lead with a number. Ask for their range first.",
                    "dollar-sign",
                    [
                        "Use their range as ceiling, not floor",
                        "Anchor to market data (levels.fyi, Glassdoor)",
                        "Negotiate in writing with clear milestones",
                    ],
                ),
                _negotiation_card(
                    "Equity & Stock",
                    "RSUs, options, and equity packages need careful analysis.",
                    "trending-up",
                    [
                        "Calculate equity value at 4-year vest + strike",
                        "Request extended cliff or front-loaded vest",
                        "Match competing offers dollar-for-dollar",
                    ],
                ),
                _negotiation_card(
                    "Signing Bonus",
                    "Guaranteed money reduces risk.",
                    "gift",
                    [
                        "Request 1.5-2x if equity is back-loaded",
                        "Cover lost bonus from quitting current job",
                        "Negotiate for immediate vest or sign-on equity",
                    ],
                ),
                _negotiation_card(
                    "Geographic Discount",
                    "Push back if they're discounting for location.",
                    "map-pin",
                    [
                        "Cost of living difference should be <15%",
                        "Reference remote salary benchmarks",
                        "Request 'location-agnostic' designation",
                    ],
                ),
                _negotiation_card(
                    "Competing Offers",
                    "The strongest leverage in any negotiation.",
                    "copy",
                    [
                        "Share only the TOTALCOMP, not exact details",
                        "Create urgency with real deadlines",
                        "Ask for 48 hours to decide after receiving any competing offer",
                    ],
                ),
                _negotiation_card(
                    "Benefits & Perks",
                    "Non-salary benefits can be worth 20-30% more.",
                    "heart",
                    [
                        "PTO, parental leave, fertility coverage",
                        "401k match and HSA contributions",
                        "Learning budget, conference attendance",
                    ],
                ),
                columns="3",
                gap="4",
            ),
            rx.heading("Script Templates", size="4", margin_top="6"),
            rx.card(
                rx.vstack(
                    rx.text("Initial Response to Offer", size="3", weight="bold"),
                    rx.box(
                        rx.text(
                            "\"Thank you for this offer. I'm excited about the team "
                            "and the problem space. I want to take a day or two to review "
                            'the details before we connect."',
                            size="2",
                            font_family="monospace",
                            color="var(--gray-11)",
                        ),
                        background="var(--gray-2)",
                        padding="3",
                        border_radius="var(--radius-2)",
                    ),
                    spacing="3",
                    align="start",
                ),
                rx.divider(),
                rx.vstack(
                    rx.text("Counter Offer Script", size="3", weight="bold"),
                    rx.box(
                        rx.text(
                            '"Based on my research and the scope of this role, '
                            "I'm targeting [X]. I have another offer at [Y], "
                            "and I'm very excited about this opportunity. "
                            'Is there flexibility to meet in the middle?"',
                            size="2",
                            font_family="monospace",
                            color="var(--gray-11)",
                        ),
                        background="var(--gray-2)",
                        padding="3",
                        border_radius="var(--radius-2)",
                    ),
                    spacing="3",
                    align="start",
                ),
                padding="4",
            ),
            rx.button(
                "Generate Custom Script",
                color_scheme="green",
                width="100%",
                margin_top="4",
            ),
            spacing="4",
            width="100%",
        ),
        on_mount=CareerState.load_applications,
    )
