from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx

from dex_studio.components.layout import page_shell


class ActivityState(rx.State):
    events: list[dict[str, Any]] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def load_activity(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None:
                self.events = []
                return
            self.events = [
                {
                    "ts": str(e.timestamp),
                    "type": e.action,
                    "message": f"{e.resource_type}/{e.resource} — {e.status}",
                }
                for e in eng.audit.get_events(limit=100)
            ]
        except Exception as exc:
            self.error = str(exc)
            self.events = []
        finally:
            self.is_loading = False


def _event_item(ev: dict[str, Any]) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.text(ev["ts"], size="1", color_scheme="gray", min_width="160px"),
            rx.badge(ev["type"], color_scheme="indigo"),
            rx.text(ev["message"], size="2"),
            spacing="3",
            align_items="center",
        ),
        padding="3",
    )


def system_activity() -> rx.Component:
    return page_shell(
        "Audit Activity",
        rx.heading("Activity Log", size="5", margin_bottom="4"),
        rx.cond(ActivityState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            ActivityState.error != "",
            rx.callout.root(
                rx.callout.text(ActivityState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        rx.cond(
            ActivityState.events.length() == 0,
            rx.callout.root(
                rx.callout.text(
                    "No recent activity. Events will appear here as the system operates."
                ),
                color_scheme="gray",
            ),
            rx.vstack(
                rx.foreach(ActivityState.events, _event_item),
                spacing="2",
            ),
        ),
        on_mount=ActivityState.load_activity,
    )
