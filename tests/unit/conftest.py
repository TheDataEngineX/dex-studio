"""Shared unit-test fixtures for DEX Studio engine helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dex_studio.engine import DexEngine

_MINIMAL_CONFIG = (
    "project:\n"
    "  name: TestProject\n"
    "  version: 0.1.0\n"
    "  description: Test config\n"
    "data:\n"
    "  engine: duckdb\n"
    "  sources:\n"
    "    test_source:\n"
    "      type: csv\n"
    "      path: /tmp/test_data\n"
    "      query: null\n"
    "      url: null\n"
    "      connection: {}\n"
    "      options: {}\n"
    "  pipelines:\n"
    "    ingest:\n"
    "      source: test_source\n"
    "      transforms: []\n"
    "      quality: null\n"
    "      destination: silver.ingest\n"
    "      target: null\n"
    "      depends_on: []\n"
    "      schedule: '0 * * * *'\n"
    "    process:\n"
    "      source: test_source\n"
    "      transforms: []\n"
    "      quality: null\n"
    "      destination: silver.process\n"
    "      target: null\n"
    "      depends_on: []\n"
    "      schedule: null\n"
)


@pytest.fixture
def engine(tmp_path: Path) -> DexEngine:
    """DexEngine backed by a minimal in-memory config — no local path dependency."""
    config_path = tmp_path / "dex.yaml"
    config_path.write_text(_MINIMAL_CONFIG)
    return DexEngine(config_path)
