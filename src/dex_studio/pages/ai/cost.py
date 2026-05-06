from __future__ import annotations

from collections.abc import AsyncGenerator

import reflex as rx

from dex_studio.components.layout import page_shell


class CostState(rx.State):
    cost_data: list[dict] = []
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def load_cost(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None or eng.ai_cost is None:
                self.cost_data = []
                return
            summary = eng.ai_cost.summary()
            self.cost_data = [
                {
                    "model": k,
                    "tokens": v.get("total_tokens", 0),
                    "cost_usd": v.get("total_cost_usd", 0.0),
                }
                for k, v in summary.get("by_model", {}).items()
            ]
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False


def _cost_row(row: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["model"]),
        rx.table.cell(row["tokens"]),
        rx.table.cell(f"${row['cost_usd']}"),
    )


def ai_cost() -> rx.Component:
    return page_shell(
        "AI Cost Tracking",
        rx.cond(CostState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            CostState.error != "",
            rx.callout.root(
                rx.callout.text(CostState.error),
                color_scheme="red",
                margin_bottom="4",
            ),
            rx.fragment(),
        ),
        rx.cond(
            CostState.cost_data.length() == 0,
            rx.callout.root(
                rx.callout.text(
                    "No cost data available. Cost tracking requires Langfuse or LiteLLM integration."
                ),
                color_scheme="gray",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Model"),
                        rx.table.column_header_cell("Tokens"),
                        rx.table.column_header_cell("Cost (USD)"),
                    )
                ),
                rx.table.body(rx.foreach(CostState.cost_data, _cost_row)),
            ),
        ),
        on_mount=CostState.load_cost,
    )
