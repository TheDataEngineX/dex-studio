"""CLI entry point for DEX Studio.

Usage::

    dex-studio                          # serve on 127.0.0.1:7860
    dex-studio --port 8080              # custom port
    dex-studio --host 127.0.0.1        # localhost only
    dex-studio --reload                 # dev mode with auto-reload
    dex-studio --version                # print version and exit
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dex-studio",
        description="DEX Studio — web UI for DataEngineX",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860, help="Bind port (default: 7860)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from dex_studio import __version__

        print(f"dex-studio {__version__}")  # noqa: T201
        sys.exit(0)

    import uvicorn

    uvicorn.run(
        "dex_studio.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
