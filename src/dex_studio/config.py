"""Configuration for DEX Studio — supports multi-project setup."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "ProjectEntry",
    "StudioConfig",
    "load_config",
    "save_config",
    "load_projects",
    "save_projects",
]

_USER_CONFIG = Path.home() / ".dex-studio" / "config.yaml"
_PROJECTS_FILE = Path.home() / ".dex-studio" / "projects.yaml"
_LOCAL_CONFIG = Path(".dex-studio.yaml")

# Fields that need coercion when sourced from env vars (strings)
_COERCE_MAP: dict[str, Callable[[str], Any]] = {
    "timeout": float,
    "poll_interval": float,
    "window_width": int,
    "window_height": int,
    "port": int,
    "native_mode": lambda v: v.lower() not in {"0", "false", "no"},
}


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    """A single project in the multi-project config."""

    name: str
    url: str = "http://localhost:17000"
    token: str | None = None
    icon: str = "folder"


@dataclass(frozen=True, slots=True)
class StudioConfig:
    """DEX Studio configuration."""

    api_url: str = "http://localhost:17000"
    api_token: str | None = None
    timeout: float = 10.0
    window_width: int = 1400
    window_height: int = 900
    theme: str = "dark"
    poll_interval: float = 5.0
    native_mode: bool = True
    host: str = "127.0.0.1"
    port: int = 7860


def load_config(
    path: Path | None = None,
    *,
    env_prefix: str = "DEX_STUDIO_",
) -> StudioConfig:
    """Load config from YAML file(s) + env vars.

    Priority (highest wins): env vars > explicit path > local > user-level > defaults.
    """
    merged: dict[str, Any] = {}

    if _USER_CONFIG.exists():
        merged.update(_load_yaml(_USER_CONFIG))
    if _LOCAL_CONFIG.exists():
        merged.update(_load_yaml(_LOCAL_CONFIG))
    if path is not None and path.exists():
        merged.update(_load_yaml(path))

    field_names = {f.name for f in StudioConfig.__dataclass_fields__.values()}
    for key in field_names:
        env_key = f"{env_prefix}{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            merged[key] = env_val

    # Coerce string values (from env or YAML parsed as strings) to correct types
    for field_name, coerce in _COERCE_MAP.items():
        if field_name in merged and isinstance(merged[field_name], str):
            merged[field_name] = coerce(merged[field_name])

    valid = {k: v for k, v in merged.items() if k in field_names}
    return StudioConfig(**valid)


def save_config(config: StudioConfig, path: Path | None = None) -> None:
    """Persist StudioConfig to ~/.dex-studio/config.yaml (or explicit path)."""
    from dataclasses import asdict

    target = path or _USER_CONFIG
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in asdict(config).items() if v is not None}
    target.write_text(yaml.safe_dump(data, default_flow_style=False))


def load_projects() -> list[ProjectEntry]:
    """Load project list from ~/.dex-studio/projects.yaml."""
    if not _PROJECTS_FILE.exists():
        return []
    data = _load_yaml(_PROJECTS_FILE)
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        return []
    return [
        ProjectEntry(
            name=name,
            **{k: v for k, v in cfg.items() if k in ("url", "token", "icon")},
        )
        for name, cfg in projects.items()
    ]


def save_projects(projects: list[ProjectEntry]) -> None:
    """Save project list to ~/.dex-studio/projects.yaml."""
    _PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "projects": {p.name: {"url": p.url, "token": p.token, "icon": p.icon} for p in projects}
    }
    _PROJECTS_FILE.write_text(yaml.safe_dump(data, default_flow_style=False))


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict on any error."""
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}
