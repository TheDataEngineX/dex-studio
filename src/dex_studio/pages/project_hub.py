from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import reflex as rx

from dex_studio.state.base import BaseState


class ProjectHubState(BaseState):
    current_project: str = ""
    project_path_input: str = ""
    new_project_name: str = ""
    new_project_path: str = ""
    show_create_modal: bool = False
    recent_projects: list[dict[str, Any]] = []
    starter_configs: list[dict[str, str]] = []

    @rx.event
    async def on_load(self) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            eng = self._engine_or_none()
            self.current_project = eng.config.project.name if eng else ""
            from dex_studio.config import load_projects

            entries = load_projects()
            self.recent_projects = [
                {"name": p.name, "icon": p.icon} for p in entries if p.name != "CareerDEX"
            ]
            from dex_studio._engine import find_starter_configs

            configs = find_starter_configs()
            self.starter_configs = [{"name": name, "path": str(path)} for name, path in configs]
        except Exception:
            self.current_project = ""
            self.recent_projects = []
            self.starter_configs = []
        finally:
            self.is_loading = False

    @rx.event
    def set_project_path(self, v: str) -> None:
        self.project_path_input = v

    @rx.event
    async def load_project(self) -> AsyncGenerator[None]:
        path = self.project_path_input.strip()
        if not path:
            return
        yield
        async for _ in self._load_by_path(path):
            yield

    @rx.event
    async def load_project_by_path(self, path: str) -> AsyncGenerator[None]:
        yield
        async for _ in self._load_by_path(path):
            yield

    async def _load_by_path(self, path: str) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                self.new_project_path = str(resolved)
                self.show_create_modal = True
                return
            from dex_studio._engine import init_engine

            eng = init_engine(resolved)
            self.current_project = eng.config.project.name
            self._push_toast(f"Loaded project: {eng.config.project.name}", "success")
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    def show_create_dialog(self) -> None:
        self.show_create_modal = True

    @rx.event
    def hide_create_dialog(self) -> None:
        self.show_create_modal = False

    @rx.event
    def set_new_project_name(self, v: str) -> None:
        self.new_project_name = v

    @rx.event
    def set_new_project_path(self, v: str) -> None:
        self.new_project_path = v

    @rx.event
    async def create_project(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            path = Path(self.new_project_path).expanduser().resolve()
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

            config_content = f"""project:
  name: {self.new_project_name or "My Project"}
  version: 0.1.0
  description: A new DataEngineX project

data:
  engine: duckdb
  sources: {{}}
  pipelines: {{}}

ml:
  tracker: builtin
  tracking:
    backend: builtin
  features:
    backend: builtin

ai:
  llm:
    provider: ollama
    model: llama3.2
  retrieval:
    strategy: hybrid
    top_k: 10
    reranker: true
  vectorstore:
    backend: builtin
    embedding_model: all-MiniLM-L6-v2

server:
  host: 0.0.0.0
  port: 17000
  auth:
    enabled: false

observability:
  metrics: true
  tracing: false
  log_level: INFO
"""
            path.write_text(config_content)
            self._push_toast(f"Created project at {path}", "success")

            from dex_studio._engine import init_engine

            eng = init_engine(path)
            self.current_project = eng.config.project.name
            self.show_create_modal = False
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False


# ── Domain navigation cards ───────────────────────────────────────────────────


def _domain_card(
    title: str,
    description: str,
    href: str,
    icon: str,
    accent: str,
) -> rx.Component:
    return rx.link(
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.icon(icon, size=20, color=f"var(--{accent}-11)"),
                        width="40px",
                        height="40px",
                        border_radius="var(--radius-2)",
                        background=f"var(--{accent}-3)",
                        border=f"1px solid var(--{accent}-5)",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.heading(title, size="3", weight="bold"),
                        rx.text(description, size="1", color="var(--gray-9)", line_height="1.5"),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="start",
                    width="100%",
                ),
                rx.hstack(
                    rx.text(
                        f"Open {title}", size="1", color=f"var(--{accent}-11)", weight="medium"
                    ),
                    rx.icon("arrow-right", size=12, color=f"var(--{accent}-11)"),
                    spacing="1",
                    align="center",
                ),
                spacing="4",
                align="start",
            ),
            padding="5",
            background="var(--gray-2)",
            border=f"1px solid var(--{accent}-4)",
            border_radius="var(--radius-3)",
            _hover={
                "background": f"var(--{accent}-2)",
                "border_color": f"var(--{accent}-7)",
                "box_shadow": f"0 4px 16px var(--{accent}-4)",
            },
            transition="all 0.15s ease",
            cursor="pointer",
        ),
        href=href,
        text_decoration="none",
        width="100%",
    )


# ── Create project dialog ─────────────────────────────────────────────────────


def _create_dialog() -> rx.Component:
    return rx.cond(
        ProjectHubState.show_create_modal,
        rx.dialog.root(
            rx.dialog.content(
                rx.vstack(
                    rx.dialog.title("Create New Project"),
                    rx.dialog.description(
                        "A dex.yaml config file will be created at the specified path.",
                        size="2",
                        color="var(--gray-9)",
                    ),
                    rx.separator(size="4"),
                    rx.vstack(
                        rx.text("Project Name", size="2", weight="medium"),
                        rx.input(
                            placeholder="My Project",
                            value=ProjectHubState.new_project_name,
                            on_change=ProjectHubState.set_new_project_name,
                            width="100%",
                            size="3",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Config Path (dex.yaml)", size="2", weight="medium"),
                        rx.input(
                            value=ProjectHubState.new_project_path,
                            on_change=ProjectHubState.set_new_project_path,
                            width="100%",
                            size="3",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.cond(
                        ProjectHubState.error != "",
                        rx.callout.root(
                            rx.callout.text(ProjectHubState.error),
                            color_scheme="red",
                            size="1",
                        ),
                        rx.fragment(),
                    ),
                    rx.hstack(
                        rx.dialog.close(
                            rx.button(
                                "Cancel",
                                on_click=ProjectHubState.hide_create_dialog,
                                variant="ghost",
                                size="2",
                            ),
                        ),
                        rx.button(
                            rx.cond(
                                ProjectHubState.is_loading,
                                rx.spinner(size="2"),
                                rx.text("Create Project"),
                            ),
                            on_click=ProjectHubState.create_project,
                            color_scheme="indigo",
                            size="2",
                            disabled=ProjectHubState.is_loading,
                        ),
                        spacing="2",
                        justify="end",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                padding="6",
                max_width="440px",
            ),
            open=ProjectHubState.show_create_modal,
            on_open_change=ProjectHubState.hide_create_dialog,
        ),
        rx.fragment(),
    )


# ── Main page ─────────────────────────────────────────────────────────────────


def project_hub() -> rx.Component:
    return rx.box(
        rx.center(
            rx.vstack(
                # ── Brand ──────────────────────────────────────────────────────
                rx.vstack(
                    rx.hstack(
                        rx.box(
                            rx.icon("zap", size=20, color="white"),
                            background="var(--indigo-9)",
                            padding="10px",
                            border_radius="var(--radius-3)",
                            display="flex",
                            align_items="center",
                            justify_content="center",
                        ),
                        rx.vstack(
                            rx.heading("DEX Studio", size="7", weight="bold"),
                            rx.text(
                                "DataEngineX — unified Data · ML · AI platform",
                                size="3",
                                color="var(--gray-9)",
                            ),
                            spacing="0",
                            align="start",
                        ),
                        spacing="4",
                        align="center",
                    ),
                    # Project status badge
                    rx.cond(
                        ProjectHubState.current_project != "",
                        rx.hstack(
                            rx.badge(
                                rx.hstack(
                                    rx.icon("circle-check", size=12),
                                    rx.text(f"Active: {ProjectHubState.current_project}"),
                                    spacing="1",
                                    align="center",
                                ),
                                color_scheme="green",
                                variant="soft",
                                radius="full",
                                size="2",
                            ),
                            rx.button(
                                "Switch",
                                on_click=lambda: rx.redirect("/onboarding"),
                                size="1",
                                variant="ghost",
                                color_scheme="gray",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.icon("circle-alert", size=14, color="var(--amber-9)"),
                            rx.text(
                                "No project loaded",
                                size="2",
                                color="var(--amber-11)",
                                weight="medium",
                            ),
                            spacing="1",
                            align="center",
                        ),
                    ),
                    spacing="4",
                    align="center",
                ),
                rx.separator(size="4"),
                # ── Domain cards (shown when project loaded) ───────────────────
                rx.cond(
                    ProjectHubState.current_project != "",
                    rx.vstack(
                        rx.text(
                            "Navigate to",
                            size="1",
                            weight="medium",
                            color="var(--gray-9)",
                            text_transform="uppercase",
                            letter_spacing="0.08em",
                        ),
                        rx.grid(
                            _domain_card(
                                "Data",
                                "Pipelines, sources, SQL, lineage and quality gates.",
                                "/data",
                                "database",
                                "indigo",
                            ),
                            _domain_card(
                                "ML",
                                "Models, experiments, features, drift and A/B tests.",
                                "/ml",
                                "brain",
                                "violet",
                            ),
                            _domain_card(
                                "AI",
                                "Agents, playground, traces, memory and workflows.",
                                "/ai",
                                "sparkles",
                                "cyan",
                            ),
                            _domain_card(
                                "System",
                                "Health, logs, metrics, components and settings.",
                                "/system",
                                "server",
                                "orange",
                            ),
                            columns="2",
                            gap="3",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                # ── Load / create project ──────────────────────────────────────
                rx.box(
                    rx.vstack(
                        # Starter examples
                        rx.cond(
                            ProjectHubState.starter_configs.length() > 0,  # type: ignore[attr-defined]
                            rx.vstack(
                                rx.text(
                                    "Example projects",
                                    size="1",
                                    weight="medium",
                                    color="var(--gray-9)",
                                    text_transform="uppercase",
                                    letter_spacing="0.08em",
                                ),
                                rx.vstack(
                                    rx.foreach(
                                        ProjectHubState.starter_configs,
                                        lambda s: rx.hstack(
                                            rx.icon("play-circle", size=15, color="var(--green-9)"),
                                            rx.vstack(
                                                rx.text(s["name"], size="2", weight="medium"),
                                                rx.text(s["path"], size="1", color="var(--gray-8)"),
                                                spacing="0",
                                            ),
                                            rx.spacer(),
                                            rx.button(
                                                "Load",
                                                on_click=lambda: (
                                                    ProjectHubState.load_project_by_path(s["path"])
                                                ),
                                                size="1",
                                                color_scheme="green",
                                                variant="soft",
                                            ),
                                            spacing="3",
                                            align="center",
                                            width="100%",
                                            padding="3",
                                            background="var(--gray-2)",
                                            border="1px solid var(--gray-4)",
                                            border_radius="var(--radius-2)",
                                        ),
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.fragment(),
                        ),
                        rx.separator(size="4"),
                        # Open by path
                        rx.vstack(
                            rx.hstack(
                                rx.icon("folder-open", size=16, color="var(--gray-9)"),
                                rx.text("Open project", size="2", weight="semibold"),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(
                                "Enter the path to a dex.yaml config file.",
                                size="2",
                                color="var(--gray-9)",
                            ),
                            rx.hstack(
                                rx.input(
                                    placeholder="/path/to/my-project/dex.yaml",
                                    value=ProjectHubState.project_path_input,
                                    on_change=ProjectHubState.set_project_path,
                                    size="3",
                                    flex="1",
                                ),
                                rx.button(
                                    "Load",
                                    on_click=ProjectHubState.load_project,
                                    loading=ProjectHubState.is_loading,
                                    size="3",
                                    color_scheme="indigo",
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            rx.cond(
                                ProjectHubState.error != "",
                                rx.callout.root(
                                    rx.callout.text(ProjectHubState.error),
                                    color_scheme="red",
                                    size="1",
                                ),
                                rx.fragment(),
                            ),
                            spacing="3",
                            align="start",
                            width="100%",
                        ),
                        rx.separator(size="4"),
                        rx.button(
                            rx.hstack(
                                rx.icon("plus", size=15),
                                rx.text("Create new project"),
                                spacing="2",
                            ),
                            on_click=ProjectHubState.show_create_dialog,
                            variant="outline",
                            size="3",
                            width="100%",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    padding="6",
                    background="var(--gray-2)",
                    border="1px solid var(--gray-4)",
                    border_radius="var(--radius-4)",
                    width="100%",
                ),
                _create_dialog(),
                spacing="6",
                width="100%",
                max_width="640px",
            ),
            padding="8",
            min_height="100vh",
            align_items="center",
        ),
        on_mount=ProjectHubState.on_load,
    )
