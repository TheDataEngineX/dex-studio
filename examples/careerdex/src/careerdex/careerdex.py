"""Reflex entry-point shim — app_name='careerdex' expects careerdex.careerdex."""

from __future__ import annotations

from careerdex.app import app  # noqa: F401  — re-exported for Reflex loader
