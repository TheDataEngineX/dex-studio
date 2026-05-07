from __future__ import annotations

from collections.abc import AsyncGenerator

import reflex as rx

from dex_studio.components.layout import page_shell


class RetrievalState(rx.State):
    query: str = ""
    results: list[dict] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def set_query(self, v: str) -> None:
        self.query = v

    @rx.event
    async def search(self) -> AsyncGenerator[None]:
        if not self.query:
            return
        self.is_loading = True
        self.error = ""
        self.results = []
        yield
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None:
                self.error = "Engine not initialized"
                return
            ltm = eng.ai_long_memory
            if ltm is not None and hasattr(ltm, "search"):
                hits = ltm.search(self.query, top_k=10)
                self.results = [
                    {"content": str(h), "source": "long_term_memory", "score": 1.0} for h in hits
                ]
            else:
                self.results = []
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False


def _result_item(result: dict) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.text(result["content"], size="2"),
            rx.hstack(
                rx.badge(result["source"], color_scheme="indigo"),
                rx.text(f"score: {result['score']}", size="1", color_scheme="gray"),
                spacing="2",
            ),
            spacing="2",
        ),
        padding="3",
    )


def ai_retrieval() -> rx.Component:
    return page_shell(
        "Retrieval",
        rx.hstack(
            rx.input(
                placeholder="Enter query...",
                value=RetrievalState.query,
                on_change=RetrievalState.set_query,
                flex="1",
            ),
            rx.button(
                rx.cond(RetrievalState.is_loading, rx.spinner(), rx.text("Search")),
                on_click=RetrievalState.search,
                color_scheme="indigo",
                disabled=RetrievalState.is_loading,
            ),
            spacing="2",
            margin_bottom="4",
        ),
        rx.cond(
            RetrievalState.error != "",
            rx.callout.root(
                rx.callout.text(RetrievalState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.cond(
            RetrievalState.results.length() == 0,
            rx.fragment(),
            rx.vstack(
                rx.foreach(RetrievalState.results, _result_item),
                spacing="3",
            ),
        ),
    )
