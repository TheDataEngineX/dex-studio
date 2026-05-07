"""DexEngine singleton — process-wide access to the dataenginex package."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dex_studio.engine import DexEngine

_ENGINE: DexEngine | None = None


def init_engine(config_path: str | Path) -> DexEngine:
    """Initialize the singleton from an explicit config path."""
    global _ENGINE
    from dex_studio.engine import DexEngine

    _ENGINE = DexEngine(config_path)
    os.environ.setdefault("DEX_CONFIG_PATH", str(config_path))
    return _ENGINE


def find_starter_configs() -> list[tuple[str, Path]]:
    """Locate all starter dex.yaml files from dex-studio examples."""
    configs: list[tuple[str, Path]] = []
    try:
        current = Path(__file__).resolve()
        # src/dex_studio/_engine.py -> repo root
        studio_root = current.parents[2]
        examples_dir = studio_root / "examples"
        if examples_dir.exists():
            for entry in examples_dir.iterdir():
                if entry.is_dir():
                    candidate = entry / "dex.yaml"
                    if candidate.exists():
                        configs.append((entry.name, candidate))
    except Exception:
        pass
    return configs


def find_starter_config() -> Path | None:
    """Locate a starter dex.yaml (backward compat — returns first found)."""
    configs = find_starter_configs()
    return configs[0][1] if configs else None


def get_engine() -> DexEngine | None:
    """Return the singleton, auto-initializing from DEX_CONFIG_PATH or starter config."""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    path = os.getenv("DEX_CONFIG_PATH")
    if path:
        return init_engine(path)
    starter = find_starter_config()
    if starter:
        return init_engine(starter)
    return None
