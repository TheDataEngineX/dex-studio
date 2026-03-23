"""CLI entry point for DEX Studio.

Usage::

    dex-studio                     # Launch with defaults
    dex-studio --url http://...:17000
    dex-studio --config path/to/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dex_studio.config import StudioConfig, load_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dex-studio",
        description="DEX Studio — local control plane for DataEngineX/DEX",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="DEX engine API URL (default: http://localhost:17000)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for authenticated DEX engine",
    )
    parser.add_argument(
        "--config",
        default=None,
        type=Path,
        help="Path to a YAML config file",
    )
    parser.add_argument(
        "--theme",
        choices=["dark", "light"],
        default=None,
        help="UI theme (default: dark)",
    )
    parser.add_argument(
        "--no-native",
        action="store_true",
        help="Open in browser instead of a native window",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project name from projects.yaml",
    )
    return parser


def _apply_project_overrides(project_name: str, overrides: dict[str, object]) -> None:
    """Resolve a project by name and write url/token into *overrides*.

    Exits with code 1 if the project is not found.
    """
    from dex_studio.config import load_projects

    projects = load_projects()
    match = [p for p in projects if p.name == project_name]
    if not match:
        print(  # noqa: T201
            f"Project '{project_name}' not found in projects.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    proj = match[0]
    overrides["api_url"] = proj.url
    if proj.token:
        overrides["api_token"] = proj.token


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from dex_studio import __version__

        print(f"dex-studio {__version__}")  # noqa: T201
        sys.exit(0)

    # Load base config (file + env)
    cfg = load_config(path=args.config)

    # Apply CLI overrides
    overrides: dict[str, object] = {}

    if args.project:
        _apply_project_overrides(args.project, overrides)

    if args.url:
        overrides["api_url"] = args.url
    if args.token:
        overrides["api_token"] = args.token
    if args.theme:
        overrides["theme"] = args.theme
    if args.no_native:
        overrides["native_mode"] = False

    if overrides:
        # Re-create with overrides (frozen dataclass)
        from dataclasses import asdict

        merged = {**asdict(cfg), **overrides}
        cfg = StudioConfig(**merged)

    # Launch the NiceGUI app
    from dex_studio.app import start

    start(config=cfg)


if __name__ == "__main__":
    main()
