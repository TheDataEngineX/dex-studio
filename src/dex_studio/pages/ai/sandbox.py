from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import reflex as rx

from dex_studio.components.layout import page_shell


class SandboxState(rx.State):
    code: str = ""
    output: str = ""
    is_loading: bool = False
    error: str = ""

    @rx.event
    async def set_code(self, v: str) -> None:
        self.code = v

    @rx.event
    async def run_code(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        self.output = ""
        yield
        try:
            from dex_studio._engine import get_engine

            eng = get_engine()
            if eng is None or eng.sandbox is None:
                self.error = "Sandbox not available — engine not initialized"
                return
            code = self.code
            result = await asyncio.to_thread(eng.sandbox.execute_code, code)
            self.output = result.stdout or result.stderr or ""
            if result.exit_code != 0 and not self.output:
                self.error = f"Exit code {result.exit_code}"
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False


def ai_sandbox() -> rx.Component:
    return page_shell(
        "Sandbox",
        rx.heading("AI Code Sandbox", size="5", margin_bottom="4"),
        rx.cond(
            SandboxState.error != "",
            rx.callout.root(
                rx.callout.text(SandboxState.error), color_scheme="red", margin_bottom="4"
            ),
            rx.fragment(),
        ),
        rx.vstack(
            rx.text_area(
                placeholder="# Enter Python code to run...",
                value=SandboxState.code,
                on_change=SandboxState.set_code,
                rows="12",
                font_family="monospace",
            ),
            rx.button(
                rx.cond(SandboxState.is_loading, rx.spinner(), rx.text("Run")),
                on_click=SandboxState.run_code,
                color_scheme="indigo",
                disabled=SandboxState.is_loading,
            ),
            rx.cond(
                SandboxState.output != "",
                rx.box(
                    rx.heading("Output", size="3", margin_bottom="2"),
                    rx.code_block(
                        SandboxState.output,
                        language="markup",
                    ),
                ),
                rx.fragment(),
            ),
            spacing="4",
        ),
    )
