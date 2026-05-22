"""Legacy shim — kept for import compatibility. Entry point is dex_studio.app:create_app."""

from __future__ import annotations

from dex_studio.app import create_app as create_app  # noqa: F401
