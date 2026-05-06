"""Reflex entry-point shim — app_name='dex_studio' expects dex_studio.dex_studio."""

from __future__ import annotations

from dex_studio.app import app  # noqa: F401  — re-exported for Reflex loader
