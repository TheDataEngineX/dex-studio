"""Shared test fixtures for DEX Studio."""

from __future__ import annotations

import pytest
from nicegui.testing.general_fixtures import (
    nicegui_reset_globals as nicegui_reset_globals,  # noqa: F401
)

from dex_studio.config import StudioConfig


@pytest.fixture()
def default_config() -> StudioConfig:
    """Return a config pointing at a dummy local URL."""
    return StudioConfig(
        api_url="http://localhost:9999",
        timeout=2.0,
    )
