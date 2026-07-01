"""DEX Studio configuration.

Two concerns:

  projects  — registry: project name → dex.yaml path  (backed by DB ``projects`` table)
  prefs     — server-side preferences                  (backed by DB ``settings`` table)

Server prefs persisted in DB: ``monthly_budget_usd``, ``default_config_path``
UI prefs (window size, native_mode): moved to browser localStorage — not stored server-side
Server config (host, port, theme): env-var only, not stored

All project config (LLM, agents, sources, pipelines) lives in the project's
own dex.yaml and is accessed through DexEngine.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ProjectEntry",
    "StudioPrefs",
    "load_prefs",
    "save_prefs",
    "load_projects",
    "save_projects",
    "add_project",
    "remove_project",
]


# ---------------------------------------------------------------------------
# Project registry  — name → dex.yaml path
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    """A registered DEX project."""

    name: str
    config_path: Path  # absolute path to the project's dex.yaml


def load_projects() -> list[ProjectEntry]:
    """Load the project registry from the database.

    Falls back to built-in defaults when the registry is empty.
    """
    from dex_studio import db_store

    rows = db_store.get_projects()
    if not rows:
        return _default_projects()

    entries: list[ProjectEntry] = []
    for name, path_str in rows:
        resolved = Path(os.path.expanduser(path_str)).resolve()
        entries.append(ProjectEntry(name=name, config_path=resolved))

    if not entries:
        return _default_projects()
    return entries


def save_projects(projects: list[ProjectEntry]) -> None:
    """Persist the project registry to the database (replace-all strategy)."""
    from dex_studio import db_store

    # Fetch current names so we can remove any that are no longer present
    existing = {name for name, _ in db_store.get_projects()}
    new_names = {p.name for p in projects}

    for name in existing - new_names:
        db_store.delete_project(name)

    for p in projects:
        db_store.set_project(p.name, str(p.config_path))


def add_project(name: str, config_path: str | Path) -> list[ProjectEntry]:
    """Add a project to the registry and persist. Returns updated list."""
    from dex_studio import db_store

    db_store.set_project(name, str(Path(config_path).resolve()))
    return load_projects()


def remove_project(name: str) -> list[ProjectEntry]:
    """Remove a project from the registry by name. Returns updated list."""
    from dex_studio import db_store

    db_store.delete_project(name)
    return load_projects()


def _default_projects() -> list[ProjectEntry]:
    """Return built-in default projects discovered from the studio examples dir."""
    from dex_studio._engine import find_starter_configs

    defaults: list[ProjectEntry] = []
    for name, path in find_starter_configs():
        defaults.append(ProjectEntry(name=name, config_path=path.resolve()))
    return defaults


# ---------------------------------------------------------------------------
# UI preferences — only server-side prefs are persisted in DB
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StudioPrefs:
    """DEX Studio preferences.

    Server-persisted (DB): monthly_budget_usd, default_config_path
    UI-only (localStorage): window_width, window_height, native_mode
    Env-var only (not stored): host, port, theme
    """

    theme: str = "dark"
    window_width: int = 1400
    window_height: int = 900
    host: str = "127.0.0.1"
    port: int = 7860
    native_mode: bool = True
    default_config_path: str = ""  # persisted across restarts
    monthly_budget_usd: float = 25.0  # AI spend budget cap shown on /system/costs


def load_prefs() -> StudioPrefs:
    """Load server-side preferences from the database."""
    from dex_studio import db_store

    kwargs: dict[str, Any] = {}

    raw_budget = db_store.get_setting("pref.monthly_budget_usd")
    if raw_budget is not None:
        with contextlib.suppress(ValueError):
            kwargs["monthly_budget_usd"] = float(raw_budget)

    raw_config = db_store.get_setting("pref.default_config_path")
    if raw_config is not None:
        kwargs["default_config_path"] = raw_config

    return StudioPrefs(**kwargs)


def save_prefs(prefs: StudioPrefs) -> None:
    """Persist server-side preferences to the database.

    Only ``monthly_budget_usd`` and ``default_config_path`` are stored.
    UI prefs (window_width, window_height, native_mode) live in localStorage.
    Server config (host, port, theme) are env-var only and never stored.
    """
    from dex_studio import db_store

    db_store.set_setting("pref.monthly_budget_usd", str(prefs.monthly_budget_usd))
    db_store.set_setting("pref.default_config_path", prefs.default_config_path)
