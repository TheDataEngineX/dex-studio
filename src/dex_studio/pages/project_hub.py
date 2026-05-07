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
        """Internal: load a project by raw path string."""
        self.is_loading = True
        self.error = ""
        yield
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                # Offer to create new project
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
        """Show the create project dialog."""
        self.show_create_modal = True

    @rx.event
    def hide_create_dialog(self) -> None:
        """Hide the create project dialog."""
        self.show_create_modal = False

    @rx.event
    def set_new_project_name(self, v: str) -> None:
        self.new_project_name = v

    @rx.event
    def set_new_project_path(self, v: str) -> None:
        self.new_project_path = v

    @rx.event
    async def create_project(self) -> AsyncGenerator[None]:
        """Create a new project with a dex.yaml."""
        self.is_loading = True
        self.error = ""
        yield
        try:
            path = Path(self.new_project_path).expanduser().resolve()
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

            # Create a minimal dex.yaml
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

            # Load the new project
            from dex_studio._engine import init_engine

            eng = init_engine(path)
            self.current_project = eng.config.project.name
            self.show_create_modal = False
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False


def _domain_card(
    title: str,
    description: str,
    href: str,
    color: str,
    icon: str,
    accent: str,
) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(icon, size=24, color=color),
                rx.heading(title, size="4"),
                spacing="3",
                align_items="center",
            ),
            rx.text(description, size="2", color_scheme="gray"),
            rx.link(
                rx.button("Open", color_scheme=accent, variant="soft", size="2"),
                href=href,
            ),
            spacing="3",
            align_items="flex-start",
        ),
        padding="5",
        width="280px",
        _hover={"box_shadow": f"0 4px 16px var(--{accent}-4)"},
        cursor="pointer",
    )


def _open_project_card() -> rx.Component:
    return rx.vstack(
        # Starter examples for quick load
        rx.cond(
            ProjectHubState.starter_configs.length() > 0,
            rx.box(
                rx.text(
                    "Examples", size="2", weight="bold", color_scheme="gray", margin_bottom="2"
                ),
                rx.flex(
                    rx.foreach(
                        ProjectHubState.starter_configs,
                        lambda starter: rx.card(
                            rx.hstack(
                                rx.icon("play", size=16, color="var(--green-9)"),
                                rx.vstack(
                                    rx.text(starter["name"], size="2", weight="medium"),
                                    rx.text(starter["path"], size="1", color_scheme="gray"),
                                    spacing="0",
                                ),
                                rx.button(
                                    "Load",
                                    on_click=lambda: ProjectHubState.load_project_by_path(
                                        starter["path"]
                                    ),
                                    size="1",
                                    color_scheme="green",
                                    variant="soft",
                                ),
                                spacing="3",
                                align_items="center",
                                width="100%",
                            ),
                            padding="3",
                            width="100%",
                        ),
                    ),
                    direction="column",
                    spacing="2",
                    width="100%",
                ),
                width="100%",
                margin_bottom="4",
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
            on_click=ProjectHubState.show_create_dialog,
            color_scheme="indigo",
            size="2",
            width="100%",
            max_width="560px",
        ),
        # Custom path input
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("folder-open", size=20, color="var(--gray-9)"),
                    rx.heading("Open Custom Project", size="4"),
                    spacing="2",
                    align_items="center",
                ),
                rx.text(
                    "Enter path to a dex.yaml to load a project.",
                    size="2",
                    color_scheme="gray",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="/path/to/my-project/dex.yaml",
                        value=ProjectHubState.project_path_input,
                        on_change=ProjectHubState.set_project_path,
                        width="340px",
                        size="2",
                    ),
                    rx.button(
                        "Load",
                        on_click=ProjectHubState.load_project,
                        loading=ProjectHubState.is_loading,
                        size="2",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    ProjectHubState.error != "",
                    rx.text(ProjectHubState.error, size="1", color="var(--red-9)"),
                    rx.fragment(),
                ),
                spacing="3",
                align_items="flex-start",
            ),
            padding="5",
            width="100%",
            max_width="560px",
        ),
        # Create Project Dialog
        rx.cond(
            ProjectHubState.show_create_modal,
            rx.dialog.root(
                rx.dialog.content(
                    rx.dialog.title("Create New Project"),
                    rx.vstack(
                        rx.text("Project Name", size="2", weight="bold"),
                        rx.input(
                            placeholder="My Project",
                            value=ProjectHubState.new_project_name,
                            on_change=ProjectHubState.set_new_project_name,
                            width="100%",
                            size="2",
                        ),
                        rx.text("Path (dex.yaml)", size="2", weight="bold"),
                        rx.input(
                            value=ProjectHubState.new_project_path,
                            on_change=ProjectHubState.set_new_project_path,
                            width="100%",
                            size="2",
                        ),
                        rx.hstack(
                            rx.spacer(),
                            rx.button(
                                "Cancel",
                                on_click=ProjectHubState.hide_create_dialog,
                                variant="ghost",
                                size="2",
                            ),
                            rx.button(
                                rx.cond(
                                    ProjectHubState.is_loading,
                                    rx.spinner(size="1"),
                                    rx.text("Create"),
                                ),
                                on_click=ProjectHubState.create_project,
                                color_scheme="indigo",
                                size="2",
                                disabled=ProjectHubState.is_loading,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    padding="6",
                    max_width="420px",
                ),
                open=ProjectHubState.show_create_modal,
                on_open_change=ProjectHubState.hide_create_dialog,
            ),
            rx.fragment(),
        ),
        spacing="3",
        width="100%",
        max_width="560px",
    )


def _active_project_badge() -> rx.Component:
    return rx.cond(
        ProjectHubState.current_project != "",
        rx.hstack(
            rx.icon("circle-check", size=14, color="var(--green-9)"),
            rx.text(
                "Active: ",
                rx.el.strong(ProjectHubState.current_project),
                size="2",
                color="var(--gray-11)",
            ),
            rx.spacer(),
            rx.button(
                "Switch Project",
                on_click=lambda: rx.redirect("/onboarding"),
                size="1",
                variant="ghost",
                color_scheme="indigo",
            ),
            spacing="1",
            align="center",
        ),
        rx.hstack(
            rx.icon("circle-alert", size=14, color="var(--orange-9)"),
            rx.text(
                "No project loaded — use the form below or ", size="2", color="var(--orange-9)"
            ),
            rx.link("open onboarding →", href="/onboarding", size="2"),
            spacing="1",
            align="center",
        ),
    )


def project_hub() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("DEX Studio", size="8", margin_bottom="1"),
            rx.text(
                "DataEngineX — unified Data · ML · AI platform",
                size="3",
                color_scheme="gray",
            ),
            _active_project_badge(),
            rx.divider(margin_y="5"),
            # Show domain cards only when project is loaded (as navigation)
            rx.cond(
                ProjectHubState.current_project != "",
                rx.flex(
                    _domain_card(
                        "Data",
                        "Pipelines, sources, SQL console, lineage, quality, catalog.",
                        "/data",
                        "var(--indigo-9)",
                        "database",
                        "indigo",
                    ),
                    _domain_card(
                        "ML",
                        "Models, experiments, features, drift, A/B testing.",
                        "/ml",
                        "var(--violet-9)",
                        "brain",
                        "violet",
                    ),
                    _domain_card(
                        "AI",
                        "Agents, playground, traces, memory, workflows, RAG.",
                        "/ai",
                        "var(--cyan-9)",
                        "bot",
                        "cyan",
                    ),
                    _domain_card(
                        "System",
                        "Health, logs, metrics, components, incidents, settings.",
                        "/system",
                        "var(--orange-9)",
                        "activity",
                        "orange",
                    ),
                    wrap="wrap",
                    gap="5",
                    justify="center",
                ),
                # When no project loaded, show empty state
                rx.vstack(
                    rx.icon("folder-open", size=40, color="var(--gray-7)"),
                    rx.text("No project loaded", size="4", weight="medium"),
                    rx.text(
                        "Load or create a project to get started", size="2", color="var(--gray-8)"
                    ),
                    rx.button(
                        "Load Project",
                        on_click=lambda: rx.redirect("/onboarding"),
                        color_scheme="indigo",
                        margin_top="3",
                    ),
                    spacing="2",
                    align="center",
                    padding_y="10",
                ),
            ),
            rx.divider(margin_y="5"),
            _open_project_card(),
            spacing="0",
            align_items="center",
        ),
        min_height="100vh",
        display="flex",
        align_items="center",
        justify_content="center",
        padding="8",
        on_mount=ProjectHubState.on_load,
    )
