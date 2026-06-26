"""Router smoke tests — verify all routes mount and return expected status codes.

Strategy:
  - No DEX_STUDIO_API_KEY set → auth disabled (auth_required always returns None)
  - get_engine() patched to return a mock DexEngine → no real dex.yaml needed
  - TestClient follows redirects by default; use allow_redirects=False to test 3xx
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_engine_mock() -> MagicMock:
    """Return a MagicMock that satisfies all DexEngine method calls in the routers."""
    eng = MagicMock()
    eng.config.project.name = "TestProject"
    eng.config.data.sources = {"src": MagicMock()}
    eng.config.ai.agents = {}
    eng.agents = {}
    eng.pipeline_stats.return_value = {"total": 2, "scheduled": 1, "failed": 0, "running": 0}
    eng.health.return_value = {"status": "ok"}
    eng.model_registry.list_models.return_value = []
    eng.warehouse_layers.return_value = [{"name": "bronze"}, {"name": "silver"}]
    eng.warehouse_tables.return_value = []
    eng.source_stats.return_value = {"rows": 0, "size_bytes": 0}
    eng.source_schema.return_value = []
    eng.source_sample.return_value = []
    eng.quality_history.return_value = {"runs": []}
    eng.pipeline_last_run.return_value = None
    eng.store.list_model_artifacts.return_value = []
    eng.store.list_experiments.return_value = []
    eng.store.list_pipeline_runs.return_value = []
    eng.store.lineage_summary.return_value = {"total_events": 0, "by_layer": {}, "by_operation": {}}
    eng.store.get_memory.return_value = []
    eng.store.get_recent_pipeline_runs.return_value = []
    eng.store.record_pipeline_run = MagicMock()
    return eng


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with auth disabled and engine mocked."""
    monkeypatch.delenv("DEX_STUDIO_API_KEY", raising=False)
    mock_eng = _make_engine_mock()
    with patch("dex_studio._engine.get_engine", return_value=mock_eng):
        from dex_studio.app import create_app

        app = create_app()
        os.environ["DEX_STUDIO_SESSION_SECRET"] = "test-secret-key-32-chars-xxxxxxx"
        return TestClient(app, raise_server_exceptions=True)


class TestOnboarding:
    def test_get_onboarding(self, client: TestClient) -> None:
        resp = client.get("/onboarding")
        assert resp.status_code == 200

    def test_login_page(self, client: TestClient) -> None:
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_logout_redirects(self, client: TestClient) -> None:
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestHub:
    def test_hub_renders(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200


class TestDataRoutes:
    def test_data_dashboard(self, client: TestClient) -> None:
        resp = client.get("/data/")
        assert resp.status_code == 200

    def test_pipelines_list(self, client: TestClient) -> None:
        resp = client.get("/data/pipelines")
        assert resp.status_code == 200

    def test_sources_list(self, client: TestClient) -> None:
        resp = client.get("/data/sources")
        assert resp.status_code == 200

    def test_warehouse(self, client: TestClient) -> None:
        resp = client.get("/data/warehouse")
        assert resp.status_code == 200

    def test_lineage(self, client: TestClient) -> None:
        resp = client.get("/data/lineage")
        assert resp.status_code == 200

    def test_quality(self, client: TestClient) -> None:
        resp = client.get("/data/quality")
        assert resp.status_code == 200

    def test_catalog(self, client: TestClient) -> None:
        resp = client.get("/data/catalog")
        assert resp.status_code == 200

    def test_sql_console(self, client: TestClient) -> None:
        resp = client.get("/data/sql")
        assert resp.status_code == 200


class TestIntelligenceRoutes:
    def test_dashboard(self, client: TestClient) -> None:
        resp = client.get("/intelligence/")
        assert resp.status_code == 200

    def test_models(self, client: TestClient) -> None:
        resp = client.get("/intelligence/models")
        assert resp.status_code == 200

    def test_experiments(self, client: TestClient) -> None:
        resp = client.get("/intelligence/experiments")
        assert resp.status_code == 200

    def test_predictions(self, client: TestClient) -> None:
        resp = client.get("/intelligence/predictions")
        assert resp.status_code == 200

    def test_features(self, client: TestClient) -> None:
        resp = client.get("/intelligence/features")
        assert resp.status_code == 200

    def test_drift(self, client: TestClient) -> None:
        resp = client.get("/intelligence/drift")
        assert resp.status_code == 200

    def test_agents(self, client: TestClient) -> None:
        resp = client.get("/intelligence/agents")
        assert resp.status_code == 200

    def test_playground(self, client: TestClient) -> None:
        resp = client.get("/intelligence/playground")
        assert resp.status_code == 200

    def test_tools(self, client: TestClient) -> None:
        resp = client.get("/intelligence/tools")
        assert resp.status_code == 200

    def test_traces(self, client: TestClient) -> None:
        resp = client.get("/intelligence/traces")
        assert resp.status_code == 200


class TestSystemRoutes:
    def test_system_status(self, client: TestClient) -> None:
        resp = client.get("/system/")
        assert resp.status_code == 200

    def test_logs(self, client: TestClient) -> None:
        resp = client.get("/system/logs")
        assert resp.status_code == 200

    def test_metrics(self, client: TestClient) -> None:
        resp = client.get("/system/metrics")
        assert resp.status_code == 200

    def test_components(self, client: TestClient) -> None:
        resp = client.get("/system/components")
        assert resp.status_code == 200
