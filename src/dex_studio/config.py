"""YAML-based configuration for DEX Studio.

Loads connection settings from ``~/.dex-studio/config.yaml`` or a
project-local ``.dex-studio.yaml``.  Environment variables override
file values (``DEX_STUDIO_API_URL``, ``DEX_STUDIO_API_TOKEN``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["StudioConfig", "load_config"]

_USER_CONFIG = Path.home() / ".dex-studio" / "config.yaml"
_LOCAL_CONFIG = Path(".dex-studio.yaml")
_DEFAULT_API_URL = "http://localhost:17000"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_WINDOW_WIDTH = 1400
_DEFAULT_WINDOW_HEIGHT = 900


@dataclass(frozen=True, slots=True)
class StudioConfig:
    """Immutable configuration for a DEX Studio session."""

    api_url: str = _DEFAULT_API_URL
    api_token: str | None = None
    timeout: float = _DEFAULT_TIMEOUT
    window_width: int = _DEFAULT_WINDOW_WIDTH
    window_height: int = _DEFAULT_WINDOW_HEIGHT
    theme: str = "dark"
    poll_interval: float = 5.0
    native_mode: bool = True
    host: str = "127.0.0.1"
    port: int = 8080


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a dict, returning ``{}`` on any error."""
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _coerce_types(merged: dict[str, Any]) -> None:
    """Coerce string values (from env vars) to their expected Python types."""
    for field, coerce in (
        ("timeout", float),
        ("poll_interval", float),
        ("window_width", int),
        ("window_height", int),
        ("port", int),
    ):
        if field in merged:
            merged[field] = coerce(merged[field])


def load_config(
    path: Path | None = None,
    *,
    env_prefix: str = "DEX_STUDIO_",
) -> StudioConfig:
    """Build config by merging file → env → explicit path.

    Priority (highest wins):
        1. Environment variables (``DEX_STUDIO_API_URL``, …)
        2. Explicit *path* argument
        3. Project-local ``.dex-studio.yaml``
        4. User-level ``~/.dex-studio/config.yaml``
        5. Built-in defaults
    """
    merged: dict[str, Any] = {}

    # Layer 1 & 2: file config (user → local → explicit)
    merged.update(_read_yaml(_USER_CONFIG))
    merged.update(_read_yaml(_LOCAL_CONFIG))
    if path is not None:
        merged.update(_read_yaml(path))

    # Layer 3: env overrides
    env_map = {
        "api_url": f"{env_prefix}API_URL",
        "api_token": f"{env_prefix}API_TOKEN",
        "timeout": f"{env_prefix}TIMEOUT",
        "theme": f"{env_prefix}THEME",
        "poll_interval": f"{env_prefix}POLL_INTERVAL",
        "host": f"{env_prefix}HOST",
        "port": f"{env_prefix}PORT",
    }
    for field_name, env_key in env_map.items():
        value = os.getenv(env_key)
        if value is not None:
            merged[field_name] = value

    _coerce_types(merged)

    # Filter to known fields only
    known = {f.name for f in StudioConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in merged.items() if k in known}

    return StudioConfig(**filtered)
