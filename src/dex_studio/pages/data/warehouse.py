from __future__ import annotations

import reflex as rx

from dex_studio.components.layout import page_shell
from dex_studio.state.data import WarehouseState


def _layer_tab(layer: str) -> rx.Component:
    return rx.button(
        layer,
        size="2",
        variant=rx.cond(WarehouseState.active_layer == layer, "solid", "outline"),
        on_click=WarehouseState.set_active_layer(layer),
    )


def data_warehouse() -> rx.Component:
    return page_shell(
        "Warehouse",
        rx.cond(
            WarehouseState.error != "",
            rx.callout.root(rx.callout.text(WarehouseState.error), color="red", margin_bottom="4"),
            rx.fragment(),
        ),
        rx.cond(WarehouseState.is_loading, rx.spinner(), rx.fragment()),
        rx.hstack(
            rx.foreach(WarehouseState.warehouse_layers, _layer_tab),
            spacing="2",
            margin_bottom="4",
        ),
        rx.heading(
            "Tables — ",
            WarehouseState.active_layer,
            size="3",
            margin_bottom="2",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Table"),
                    rx.table.column_header_cell("Rows"),
                    rx.table.column_header_cell("Size"),
                    rx.table.column_header_cell("Updated"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    WarehouseState.warehouse_tables,
                    lambda t: rx.table.row(
                        rx.table.cell(t["name"]),
                        rx.table.cell(t["rows"]),
                        rx.table.cell(t["size"]),
                        rx.table.cell(t["updated"]),
                    ),
                )
            ),
            width="100%",
        ),
        on_mount=[WarehouseState.load_warehouse_layers, WarehouseState.load_warehouse_tables],
    )
