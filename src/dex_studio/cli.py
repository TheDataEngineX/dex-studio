"""CLI entry point for DEX Studio.

Usage::

    dex-studio                          # serve on 0.0.0.0:7860
    dex-studio --port 8080              # custom port
    dex-studio --host 127.0.0.1         # localhost only
    dex-studio --reload                 # dev mode with auto-reload
    dex-studio --version                # print version and exit
"""

from __future__ import annotations

import argparse
import os
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


class _EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    database_url: str = ""
    dex_studio_session_secret: str = ""
    dex_studio_passphrase: str = ""
    dex_config_path: str = ""
    dex_https: bool = False
    dex_trusted_proxies: int = 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dex-studio",
        description="DEX Studio — web UI for DataEngineX",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
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

    cfg = _EnvSettings()
    for k, v in cfg.model_dump().items():
        os.environ.setdefault(k.upper(), str(v))
    for k, v in (cfg.__pydantic_extra__ or {}).items():
        os.environ.setdefault(k.upper(), str(v))

    uvicorn.run(
        "dex_studio.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
