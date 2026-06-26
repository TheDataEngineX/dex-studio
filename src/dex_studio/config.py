"""DEX Studio configuration.

Two files, two concerns:

  ~/.dex-studio/projects.yaml   — registry: project name → dex.yaml path
  ~/.dex-studio/prefs.yaml      — UI preferences (theme, window size, nothing else)

All project config (LLM, agents, sources, pipelines) lives in the project's
own dex.yaml and is accessed through DexEngine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "ProjectEntry",
    "StudioPrefs",
    "load_prefs",
    "save_prefs",
    "load_projects",
    "save_projects",
]

_STUDIO_DIR = Path.home() / ".dex-studio"
_PROJECTS_FILE = _STUDIO_DIR / "projects.yaml"
_PREFS_FILE = _STUDIO_DIR / "prefs.yaml"


# ---------------------------------------------------------------------------
# Project registry  — name → dex.yaml path
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    """A registered DEX project."""

    name: str
    config_path: Path  # absolute path to the project's dex.yaml


def load_projects() -> list[ProjectEntry]:
    """Load the project registry from ~/.dex-studio/projects.yaml.

    Format::

        projects:
          careerdex: ~/projects/careerdex/dex.yaml
          moviedex: /data/pipelines/moviedex/dex.yaml
    """
    if not _PROJECTS_FILE.exists():
        return _default_projects()

    data = _load_yaml(_PROJECTS_FILE)
    raw = data.get("projects", {})
    if not isinstance(raw, dict):
        return _default_projects()

    entries: list[ProjectEntry] = []
    for name, path_str in raw.items():
        resolved = Path(os.path.expanduser(str(path_str))).resolve()
        entries.append(ProjectEntry(name=str(name), config_path=resolved))

    if not entries:
        return _default_projects()
    return entries


def save_projects(projects: list[ProjectEntry]) -> None:
    """Persist the project registry to ~/.dex-studio/projects.yaml."""
    _STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"projects": {p.name: str(p.config_path) for p in projects}}
    _PROJECTS_FILE.write_text(yaml.safe_dump(data, default_flow_style=False))


def add_project(name: str, config_path: str | Path) -> list[ProjectEntry]:
    """Add a project to the registry and persist. Returns updated list."""
    projects = load_projects()
    projects = [p for p in projects if p.name != name]  # replace if exists
    projects.append(ProjectEntry(name=name, config_path=Path(config_path).resolve()))
    save_projects(projects)
    return projects


def remove_project(name: str) -> list[ProjectEntry]:
    """Remove a project from the registry by name. Returns updated list."""
    projects = [p for p in load_projects() if p.name != name]
    save_projects(projects)
    return projects


def _default_projects() -> list[ProjectEntry]:
    """Return built-in default projects discovered from the studio examples dir."""
    from dex_studio._engine import find_starter_configs

    defaults: list[ProjectEntry] = []
    for name, path in find_starter_configs():
        defaults.append(ProjectEntry(name=name, config_path=path.resolve()))
    return defaults


# ---------------------------------------------------------------------------
# UI preferences — theme, window size, nothing else
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StudioPrefs:
    """DEX Studio UI preferences."""

    theme: str = "dark"
    window_width: int = 1400
    window_height: int = 900
    host: str = "127.0.0.1"
    port: int = 7860
    native_mode: bool = True
    default_config_path: str = ""  # persisted across restarts
    monthly_budget_usd: float = 25.0  # AI spend budget cap shown on /system/costs


def load_prefs() -> StudioPrefs:
    """Load UI preferences from ~/.dex-studio/prefs.yaml."""
    data = _load_yaml(_PREFS_FILE) if _PREFS_FILE.exists() else {}
    _COERCE: dict[str, Any] = {
        "window_width": int,
        "window_height": int,
        "port": int,
        "monthly_budget_usd": float,
        "native_mode": lambda v: str(v).lower() not in {"0", "false", "no"},
    }
    for key, coerce in _COERCE.items():
        if key in data and isinstance(data[key], str):
            data[key] = coerce(data[key])

    valid_keys = set(StudioPrefs.__dataclass_fields__)
    return StudioPrefs(**{k: v for k, v in data.items() if k in valid_keys})


def save_prefs(prefs: StudioPrefs) -> None:
    """Persist UI preferences to ~/.dex-studio/prefs.yaml."""
    from dataclasses import asdict

    _STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    _PREFS_FILE.write_text(
        yaml.safe_dump(
            {k: v for k, v in asdict(prefs).items() if v is not None},
            default_flow_style=False,
        )
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}
