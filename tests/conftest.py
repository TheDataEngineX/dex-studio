"""Shared test fixtures for DEX Studio."""

from __future__ import annotations

import pytest

from dex_studio.config import StudioConfig


@pytest.fixture()
def default_config() -> StudioConfig:
    """Return a config pointing at a dummy local URL."""
    return StudioConfig(
        api_url="http://localhost:9999",
        timeout=2.0,
    )
