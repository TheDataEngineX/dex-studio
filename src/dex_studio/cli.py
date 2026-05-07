"""CLI entry point for DEX Studio.

Usage::

    dex-studio my-project/dex.yaml          # local mode (default)
    dex-studio --project staging            # named project from ~/.dex-studio/projects.yaml
    dex-studio --url http://dex:17000       # explicit remote URL
    dex-studio                               # looks for dex.yaml in CWD
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import dex_studio.config as _dex_cfg
from dex_studio.config import StudioConfig, load_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dex-studio",
        description="DEX Studio — local control plane for DataEngineX",
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=None,
        help="Path to a dex YAML config file (default: dex.yaml in CWD)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Named project from ~/.dex-studio/projects.yaml",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="DEX engine API URL (overrides project lookup)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Auth token for the DEX engine API",
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
    return parser


def _resolve_config(args: argparse.Namespace) -> tuple[StudioConfig, bool]:
    """Return (StudioConfig, is_http_mode) from parsed args."""
    from dataclasses import asdict

    ui_cfg = load_config()
    overrides: dict[str, object] = {}

    if args.project:
        projects = _dex_cfg.load_projects()
        match = next((p for p in projects if p.name == args.project), None)
        if match is None:
            sys.stderr.write(f"Project '{args.project}' not found in projects config.\n")
            sys.exit(1)
        overrides["api_url"] = match.url
        if match.token:
            overrides["api_token"] = match.token

    # --url / --token override project lookup
    overrides.update({k: v for k, v in [("api_url", args.url), ("api_token", args.token)] if v})
    overrides.update({k: v for k, v in [("theme", args.theme)] if v})
    if args.no_native:
        overrides["native_mode"] = False

    if overrides:
        ui_cfg = StudioConfig(**{**asdict(ui_cfg), **overrides})

    return ui_cfg, bool(args.project or args.url)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from dex_studio import __version__

        print(f"dex-studio {__version__}")  # noqa: T201
        sys.exit(0)

    ui_cfg, http_mode = _resolve_config(args)

    from dex_studio.app import start

    if http_mode:
        start(config=ui_cfg)
    else:
        start(config_path=args.config, studio_config=ui_cfg)


if __name__ == "__main__":
    main()
