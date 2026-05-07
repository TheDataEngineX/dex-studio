from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import reflex as rx


class OnboardingState(rx.State):
    config_path: str = ""
    starter_configs: list[dict[str, str]] = []  # [{name, path, description}]
    ping_status: str = ""
    ping_latency: float = 0.0
    is_loading: bool = False
    error: str = ""

    @rx.event
    def on_load(self) -> None:
        from dex_studio._engine import find_starter_configs

        configs = find_starter_configs()
        self.starter_configs = [
            {
                "name": name,
                "path": str(path),
                "description": _starter_description(name),
            }
            for name, path in configs
        ]
        # Default to first starter if no config set yet
        if not self.config_path and self.starter_configs:
            self.config_path = self.starter_configs[0]["path"]

    @rx.event
    async def set_config_path(self, v: str) -> None:
        self.config_path = v

    @rx.event
    async def load_starter(self, path: str) -> AsyncGenerator[None]:
        self.config_path = path
        yield
        async for _ in self.test_connection():  # type: ignore[attr-defined]
            yield

    @rx.event
    async def test_connection(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        self.ping_status = ""
        yield
        start = time.monotonic()
        try:
            from dex_studio._engine import get_engine, init_engine

            eng = get_engine()
            if eng is None and self.config_path:
                eng = init_engine(self.config_path)
            if eng is None:
                self.ping_status = "no config"
                self.error = "Enter a path to a dex.yaml config file."
                return
            eng.health()
            self.ping_latency = round((time.monotonic() - start) * 1000, 1)
            self.ping_status = "online"
        except Exception as exc:
            self.error = str(exc)
            self.ping_status = "error"
        finally:
            self.is_loading = False


def _step(number: str, title: str, body: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.text(number, size="3", weight="bold", color_scheme="indigo"),
            width="32px",
            height="32px",
            border_radius="full",
            background="var(--indigo-3)",
            display="flex",
            align_items="center",
            justify_content="center",
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(title, size="3", weight="bold"),
            rx.text(body, size="2", color_scheme="gray"),
            spacing="1",
            align_items="flex-start",
        ),
        spacing="3",
        align_items="flex-start",
    )


def onboarding() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("Welcome to DEX Studio", size="7", margin_bottom="2"),
            rx.text(
                "Self-hosted control plane for your DataEngineX platform.",
                size="3",
                color_scheme="gray",
                margin_bottom="6",
            ),
            # Starter projects — from examples/ directory
            rx.cond(
                OnboardingState.starter_configs.length() > 0,
                rx.vstack(
                    rx.heading("Starter Projects", size="4", margin_bottom="2"),
                    rx.foreach(
                        OnboardingState.starter_configs,
                        lambda starter: rx.card(
                            rx.vstack(
                                rx.hstack(
                                    rx.badge("Example", color_scheme="green", variant="soft"),
                                    rx.heading(starter["name"], size="3"),
                                    spacing="2",
                                    align_items="center",
                                ),
                                rx.text(starter["description"], size="2", color_scheme="gray"),
                                rx.code(starter["path"], size="1", color_scheme="gray"),
                                rx.hstack(
                                    rx.button(
                                        rx.cond(
                                            OnboardingState.is_loading,
                                            rx.spinner(),
                                            rx.hstack(
                                                rx.icon("zap", size=14),
                                                rx.text("Load"),
                                                spacing="2",
                                            ),
                                        ),
                                        on_click=lambda: OnboardingState.load_starter(
                                            starter["path"]
                                        ),
                                        color_scheme="green",
                                        size="2",
                                        disabled=OnboardingState.is_loading,
                                    ),
                                    rx.cond(
                                        OnboardingState.ping_status == "online",
                                        rx.hstack(
                                            rx.badge("Ready", color_scheme="green"),
                                            rx.text(
                                                OnboardingState.ping_latency,
                                                size="2",
                                                color_scheme="gray",
                                            ),
                                            rx.text("ms", size="2", color_scheme="gray"),
                                            rx.link(
                                                rx.button(
                                                    "Open Hub →", color_scheme="indigo", size="2"
                                                ),
                                                href="/",
                                            ),
                                            spacing="2",
                                            align_items="center",
                                        ),
                                        rx.fragment(),
                                    ),
                                    spacing="3",
                                    align_items="center",
                                ),
                                rx.cond(
                                    OnboardingState.error != "",
                                    rx.callout.root(
                                        rx.callout.text(OnboardingState.error),
                                        color_scheme="red",
                                    ),
                                    rx.fragment(),
                                ),
                                spacing="3",
                                width="100%",
                            ),
                            padding="4",
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                    max_width="520px",
                ),
                rx.fragment(),
            ),
            # Create New Project button
            rx.button(
                rx.hstack(
                    rx.icon("plus", size=16),
                    rx.text("Create New Project"),
                    spacing="2",
                ),
                on_click=lambda: rx.redirect("/"),  # Go to hub where create dialog is
                color_scheme="indigo",
                size="2",
                variant="outline",
                margin_top="3",
            ),
            # Custom config
            rx.card(
                rx.vstack(
                    rx.heading("Custom Project", size="4", margin_bottom="3"),
                    rx.hstack(
                        rx.input(
                            value=OnboardingState.config_path,
                            on_change=OnboardingState.set_config_path,
                            placeholder="/path/to/dex.yaml",
                            width="320px",
                        ),
                        rx.button(
                            rx.cond(
                                OnboardingState.is_loading,
                                rx.spinner(),
                                rx.text("Load"),
                            ),
                            on_click=OnboardingState.test_connection,
                            color_scheme="indigo",
                            disabled=OnboardingState.is_loading,
                        ),
                        spacing="2",
                        align_items="center",
                    ),
                    rx.cond(
                        OnboardingState.ping_status == "online",
                        rx.link(
                            rx.button("Open Hub →", color_scheme="indigo", size="2"),
                            href="/",
                        ),
                        rx.fragment(),
                    ),
                    spacing="4",
                    width="100%",
                ),
                padding="6",
                width="100%",
                max_width="520px",
            ),
            # Quick start
            rx.card(
                rx.vstack(
                    rx.heading("Quick Start", size="4", margin_bottom="3"),
                    _step(
                        "1", "Configure dex.yaml", "Define data sources, ML models, and AI agents."
                    ),
                    _step(
                        "2",
                        "Load config above",
                        "Point Studio at your dex.yaml to initialize the engine.",
                    ),
                    _step(
                        "3", "Explore domains", "Navigate to Data, ML, AI, or System from the hub."
                    ),
                    _step(
                        "4",
                        "Run the AI Playground",
                        "Chat with your configured agents at /ai/playground.",
                    ),
                    spacing="4",
                    width="100%",
                ),
                padding="6",
                width="100%",
                max_width="520px",
            ),
            rx.link(
                rx.button("Skip to Hub", variant="ghost", size="2"),
                href="/",
            ),
            spacing="5",
            align_items="center",
        ),
        min_height="100vh",
        display="flex",
        align_items="center",
        justify_content="center",
        padding="8",
    )


def _starter_description(name: str) -> str:
    """Return a human-readable description for a starter project."""
    descriptions = {
        "ecommerce": "Full-stack e-commerce analytics: pipelines, quality gates, ML training, drift detection, RAG, and lineage.",
        "movie-dex": "Movie recommendation engine: data pipelines, genre analysis, ML experiments, and AI agents for movie discovery.",
    }
    return descriptions.get(name, "A DataEngineX starter project.")
