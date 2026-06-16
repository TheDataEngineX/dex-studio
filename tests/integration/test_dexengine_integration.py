"""Integration tests — dex-studio FastAPI app wired to a real DexEngine.

Tests the full request/response cycle without mocks:
  - App created via create_app()
  - DexEngine initialised from a minimal in-memory config written to a tmp file
  - Singleton injected directly into dex_studio._engine._ENGINE
  - FastAPI TestClient used to exercise routes end-to-end

Routes verified against the registered route list — no guessing.
"""

from __future__ import annotations

import csv
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Minimal dex.yaml with a real CSV source ──────────────────────────────────

_CONFIG_TEMPLATE = """\
project:
  name: IntegrationTest
  version: 0.1.0
  description: Integration test project

data:
  engine: duckdb
  sources:
    users:
      type: csv
      path: {csv_path}
      query: null
      url: null
      connection: {{}}
      options: {{}}
  pipelines:
    clean_users:
      source: users
      transforms:
        - type: filter
          condition: "age > 0"
      quality: null
      destination: silver.users
      target: null
      depends_on: []
      schedule: null
"""


@pytest.fixture(scope="module")
def csv_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("data")
    p = d / "users.csv"
    with p.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "age"])
        writer.writerow([1, "Alice", 30])
        writer.writerow([2, "Bob", 25])
        writer.writerow([3, "Charlie", -1])
    return p


@pytest.fixture(scope="module")
def real_engine(csv_source: Path, tmp_path_factory: pytest.TempPathFactory):
    from dataenginex.engine import DexEngine

    cfg = tmp_path_factory.mktemp("cfg") / "dex.yaml"
    cfg.write_text(_CONFIG_TEMPLATE.format(csv_path=csv_source))
    return DexEngine(cfg)


_TEST_API_KEY = "integration-test-key-abc123"  # gitleaks:allow


@pytest.fixture(scope="module")
def client(real_engine) -> Generator[TestClient]:
    """TestClient with real DexEngine injected, scheduler lifespan disabled.

    Auth is always enabled now, so we set a known test key and login once
    before yielding so all tests run in an authenticated session.
    """
    import dex_studio._engine as _mod

    orig = _mod._ENGINE
    _mod._ENGINE = real_engine
    os.environ["DEX_STUDIO_API_KEY"] = _TEST_API_KEY
    os.environ.setdefault("DEX_STUDIO_SESSION_SECRET", "t" * 32)

    from dex_studio.app import create_app

    @asynccontextmanager
    async def _noop_lifespan(_app: object) -> AsyncGenerator[None]:
        yield

    app = create_app()
    app.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]

    with TestClient(app, raise_server_exceptions=False) as tc:
        # Authenticate once — the TestClient persists the session cookie.
        login = tc.post("/login", data={"api_key": _TEST_API_KEY})
        assert login.status_code in (200, 303), f"Login failed: {login.status_code}"
        yield tc

    _mod._ENGINE = orig
    os.environ.pop("DEX_STUDIO_API_KEY", None)


@pytest.fixture(scope="module")
def csrf_headers(client: TestClient) -> dict[str, str]:
    """Extract the CSRF token from a GET page and return it as a header dict."""
    import re

    r = client.get("/data/sources")
    match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', r.content)
    assert match, "CSRF meta tag not found — is base.html injecting it?"
    return {"X-CSRF-Token": match.group(1).decode()}


# ── Health ────────────────────────────────────────────────────────────────────


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "healthy")


# ── Root ──────────────────────────────────────────────────────────────────────


def test_home_renders(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert b"IntegrationTest" in r.content


# ── Data — sources ────────────────────────────────────────────────────────────


def test_sources_page(client: TestClient) -> None:
    r = client.get("/data/sources")
    assert r.status_code == 200


def test_source_detail(client: TestClient) -> None:
    r = client.get("/data/sources/users")
    assert r.status_code == 200


# ── Data — pipelines ─────────────────────────────────────────────────────────


def test_pipelines_page(client: TestClient) -> None:
    r = client.get("/data/pipelines")
    assert r.status_code == 200


def test_pipeline_run(client: TestClient, csrf_headers: dict[str, str]) -> None:
    r = client.post("/data/pipelines/run/clean_users", headers=csrf_headers)
    assert r.status_code in (200, 303)


def test_pipeline_run_unknown(client: TestClient, csrf_headers: dict[str, str]) -> None:
    r = client.post("/data/pipelines/run/nonexistent", headers=csrf_headers)
    assert r.status_code in (200, 303, 404, 422, 500)


# ── Data — warehouse ──────────────────────────────────────────────────────────


def test_warehouse_page(client: TestClient) -> None:
    r = client.get("/data/warehouse")
    assert r.status_code == 200


def test_warehouse_tables(client: TestClient) -> None:
    r = client.get("/data/warehouse/tables")
    assert r.status_code == 200


# ── Data — quality ────────────────────────────────────────────────────────────


def test_quality_page(client: TestClient) -> None:
    r = client.get("/data/quality")
    assert r.status_code == 200


# ── Data — SQL ────────────────────────────────────────────────────────────────


def test_sql_page(client: TestClient) -> None:
    r = client.get("/data/sql")
    assert r.status_code == 200


def test_sql_execute(client: TestClient, csrf_headers: dict[str, str]) -> None:
    r = client.post("/data/sql/execute", data={"query": "SELECT 1 AS n"}, headers=csrf_headers)
    assert r.status_code == 200
    assert b"1" in r.content


# ── Data — lineage ────────────────────────────────────────────────────────────


def test_lineage_page(client: TestClient) -> None:
    r = client.get("/data/lineage")
    assert r.status_code == 200


# ── System ────────────────────────────────────────────────────────────────────


def test_system_status(client: TestClient) -> None:
    r = client.get("/system/status")
    assert r.status_code == 200


def test_system_logs(client: TestClient) -> None:
    r = client.get("/system/logs")
    assert r.status_code == 200


def test_system_metrics(client: TestClient) -> None:
    r = client.get("/system/metrics")
    assert r.status_code == 200


# ── ML ────────────────────────────────────────────────────────────────────────


def test_ml_models(client: TestClient) -> None:
    r = client.get("/ml/models")
    assert r.status_code == 200


def test_ml_experiments(client: TestClient) -> None:
    r = client.get("/ml/experiments")
    assert r.status_code == 200


def test_ml_drift(client: TestClient) -> None:
    r = client.get("/ml/drift")
    assert r.status_code == 200


# ── AI ────────────────────────────────────────────────────────────────────────


def test_ai_agents(client: TestClient) -> None:
    r = client.get("/ai/agents")
    assert r.status_code == 200


def test_ai_playground(client: TestClient) -> None:
    r = client.get("/ai/playground")
    assert r.status_code == 200
