from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.ml import MLState


class PromotionsState(MLState):
    promotions: list[dict] = []

    @rx.event
    async def load_promotions(self) -> None:
        self.is_loading = True
        self.error = ""
        yield
        data = await self._get("/api/v1/ml/promotions")
        self.promotions = data.get("promotions", [])
        self.is_loading = False


def ml_promotions() -> rx.Component:
    return page_shell(
        "Model Promotions",
        rx.cond(
            PromotionsState.error != "",
            rx.callout.root(rx.callout.text(PromotionsState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(PromotionsState.is_loading, rx.spinner(), rx.fragment()),
        rx.cond(
            PromotionsState.promotions.length() > 0,  # type: ignore[attr-defined]
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Model"),
                        rx.table.column_header_cell("From"),
                        rx.table.column_header_cell("To"),
                        rx.table.column_header_cell("Approved By"),
                        rx.table.column_header_cell("Date"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        PromotionsState.promotions,
                        lambda p: rx.table.row(
                            rx.table.cell(p["model"]),
                            rx.table.cell(p["from_stage"]),
                            rx.table.cell(p["to_stage"]),
                            rx.table.cell(p["approved_by"]),
                            rx.table.cell(p["date"]),
                        ),
                    )
                ),
                width="100%",
            ),
            rx.callout.root(
                rx.callout.text(
                    "No promotion history yet. Promote a model from the Model Registry."
                ),
                color="blue",
            ),
        ),
        on_mount=PromotionsState.load_promotions,
    )
