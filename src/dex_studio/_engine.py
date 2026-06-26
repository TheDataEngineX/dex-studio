"""DexEngine singleton — process-wide access to the dataenginex library.

DexEngine now lives in dataenginex itself. This module manages the singleton
instance for the dex-studio process and provides project discovery helpers.
"""

from __future__ import annotations

import os
import threading
from contextlib import suppress
from pathlib import Path

from dataenginex.engine import DexEngine

_ENGINE: DexEngine | None = None
# Protects _ENGINE mutation. DexEngine.__init__ is synchronous and potentially
# slow (ML model loading, vector ingest). The lock prevents two concurrent
# project-switch requests from racing and leaving a half-initialised singleton.
_ENGINE_LOCK = threading.Lock()

# Project storage directory — only dex.yaml paths are stored here
USER_PROJECTS_DIR: Path = Path.home() / ".dex-studio" / "projects"
_CONFIG_FILENAME = "dex.yaml"


def init_engine(config_path: str | Path) -> DexEngine:
    """Initialize the singleton from an explicit config path.

    Closes the previous engine before replacing it so SQLite connections
    are released. Guarded by a thread lock to prevent concurrent init races.
    """
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            with suppress(Exception):
                _ENGINE.close()
        _ENGINE = DexEngine(config_path)
        os.environ["DEX_CONFIG_PATH"] = str(config_path)
        return _ENGINE


def get_engine() -> DexEngine | None:
    """Return the singleton, auto-initializing from DEX_CONFIG_PATH or saved default."""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    path = os.getenv("DEX_CONFIG_PATH")
    if path:
        return init_engine(path)
    # Saved default project (persisted via StudioPrefs.default_config_path)
    try:
        from dex_studio.config import load_prefs  # lazy to avoid circular import

        saved = load_prefs().default_config_path
        if saved:
            p = Path(saved)
            if p.exists():
                return init_engine(p)
    except Exception:
        pass
    user = find_user_projects()
    if user:
        return init_engine(user[0][1])
    starter = find_starter_config()
    if starter:
        return init_engine(starter)
    return None


def find_user_projects() -> list[tuple[str, Path]]:
    """Scan ~/.dex-studio/projects/ for dex.yaml files."""
    projects: list[tuple[str, Path]] = []
    try:
        if USER_PROJECTS_DIR.exists():
            for entry in sorted(USER_PROJECTS_DIR.iterdir()):
                if entry.is_dir():
                    candidate = entry / _CONFIG_FILENAME
                    if candidate.exists():
                        projects.append((entry.name, candidate))
    except Exception:
        pass
    return projects


def find_starter_configs() -> list[tuple[str, Path]]:
    """Locate starter dex.yaml files from dex-studio examples."""
    configs: list[tuple[str, Path]] = []
    try:
        studio_root = Path(__file__).resolve().parents[2]
        examples_dir = studio_root / "examples"
        if examples_dir.exists():
            for entry in sorted(examples_dir.iterdir()):
                if entry.is_dir():
                    candidate = entry / _CONFIG_FILENAME
                    if candidate.exists():
                        configs.append((entry.name, candidate))
    except Exception:
        pass
    return configs


def find_starter_config() -> Path | None:
    configs = find_starter_configs()
    return configs[0][1] if configs else None


def copy_example_to_user_dir(example_yaml: Path) -> Path:
    """Copy an example project to ~/.dex-studio/projects/ and return the new dex.yaml path."""
    import shutil

    example_dir = example_yaml.parent
    dest_dir = USER_PROJECTS_DIR / example_dir.name
    if not dest_dir.exists():
        USER_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(example_dir, dest_dir)
    return dest_dir / _CONFIG_FILENAME


def validate_config_file(config_path: str | Path) -> tuple[list[str], list[str]]:
    """Validate a dex.yaml before engine initialisation."""
    from dataenginex.config import load_config, validate_config
    from dataenginex.config.loader import ConfigError  # type: ignore[attr-defined]

    try:
        config = load_config(Path(config_path))  # noqa: S603
    except ConfigError as exc:
        return ([str(exc)], [])
    except FileNotFoundError as exc:
        return ([f"File not found: {exc}"], [])
    except Exception as exc:
        return ([f"Failed to read config: {exc}"], [])

    warnings = validate_config(config)
    return ([], warnings)
