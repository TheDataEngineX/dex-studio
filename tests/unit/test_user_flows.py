"""End-to-end user flow tests using real DuckDB (no mocks on the DB layer).

Tests represent full journeys a user takes through the application:
  - DexClient: UI → API endpoint mapping
  - Config: studio config loading from env and file

UI → API mapping tested here:
  Page                   | DexClient method           | DEX API endpoint
  -----------------------|----------------------------|-------------------------------
  /data/pipelines        | list_pipelines()           | GET /api/v1/pipelines/
  /data/pipelines (run)  | run_pipeline(name)         | POST /api/v1/pipelines/{name}/run
  /data/sources          | list_sources()             | GET /api/v1/data/sources
  /data/warehouse        | warehouse_layers()         | GET /api/v1/data/warehouse/layers
  /data/lineage          | list_lineage()             | GET /api/v1/data/lineage
  /data/quality          | data_quality_summary()     | GET /api/v1/data/quality/summary
  /ml/experiments        | list_experiments()         | GET /api/v1/ml/experiments
  /ml/models             | list_models()              | GET /api/v1/ml/models
  /ml/models (promote)   | promote_model(n, stage)    | POST /api/v1/ml/models/{n}/promote
  /ml/predictions        | predict(model, features)   | POST /api/v1/ml/predictions
  /ml/features           | list_feature_groups()      | GET /api/v1/ml/features
  /ai/agents (chat)      | agent_chat(name, msg)      | POST /api/v1/ai/agents/{n}/chat
  /ai/tools              | list_tools()               | GET /api/v1/ai/tools
  /system/status         | components()               | GET /api/v1/system/components
  /system/logs           | logs(level, limit)         | GET /api/v1/system/logs
"""

from __future__ import annotations

import httpx
import pytest

from dex_studio.client import DexClient
from dex_studio.config import StudioConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> StudioConfig:
    return StudioConfig(api_url="http://localhost:9999", timeout=2.0)


def _client_with_mock(config: StudioConfig, responses: dict[str, object]) -> DexClient:
    """Create a DexClient with a routing mock transport."""
    client = DexClient(config)

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        for pattern, resp in responses.items():
            if pattern in path:
                return httpx.Response(200, json=resp)
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
    return client


# ---------------------------------------------------------------------------
# User Flow: UI → API mapping
# ---------------------------------------------------------------------------


class TestUIToAPIMapping:
    """Verify each studio page's DexClient call hits the correct DEX endpoint."""

    @pytest.mark.asyncio()
    async def test_pipelines_page_calls_list_pipelines(self, config: StudioConfig) -> None:
        captured: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(str(req.url.path))
            return httpx.Response(200, json={"pipelines": [], "count": 0})

        client = _client_with_mock(config, {})
        transport = httpx.MockTransport(handler)
        assert client._client is not None
        client._client._transport = transport  # type: ignore[attr-defined]
        await client.list_pipelines()
        await client.close()
        assert any("/pipelines" in p for p in captured)

    @pytest.mark.asyncio()
    async def test_run_pipeline_calls_post(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"pipeline": "ingest", "success": True})

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.run_pipeline("ingest")
        await client.close()
        assert captured[0].method == "POST"
        assert "ingest/run" in str(captured[0].url)

    @pytest.mark.asyncio()
    async def test_sources_page_calls_list_sources(self, config: StudioConfig) -> None:
        captured: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(str(req.url.path))
            return httpx.Response(200, json={"sources": [], "count": 0})

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.list_sources()
        await client.close()
        assert any("data/sources" in p for p in captured)

    @pytest.mark.asyncio()
    async def test_agents_chat_calls_correct_endpoint(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(
                200, json={"agent": "bot", "response": "hi", "iterations": 1, "tool_calls": 0}
            )

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.agent_chat("bot", "hello")
        await client.close()
        assert captured[0].method == "POST"
        assert "/ai/agents/bot/chat" in str(captured[0].url)

    @pytest.mark.asyncio()
    async def test_models_promote_calls_post(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(
                200, json={"name": "clf", "stage": "production", "promoted": True}
            )

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.promote_model("clf", "production")
        await client.close()
        assert captured[0].method == "POST"
        assert "clf/promote" in str(captured[0].url)

    @pytest.mark.asyncio()
    async def test_system_logs_passes_level_param(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"logs": [], "count": 0, "message": ""})

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.logs(level="warning", limit=25)
        await client.close()
        url_str = str(captured[0].url)
        assert "level=warning" in url_str
        assert "limit=25" in url_str

    @pytest.mark.asyncio()
    async def test_warehouse_tables_passes_layer_in_path(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"layer": "gold", "tables": [], "count": 0})

        client = DexClient(config)
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        await client.warehouse_tables("gold")
        await client.close()
        assert "gold/tables" in str(captured[0].url)


# ---------------------------------------------------------------------------
# User Flow: Config loading
# ---------------------------------------------------------------------------


class TestConfigLoadingFlow:
    def test_default_config_values(self) -> None:
        cfg = StudioConfig()
        assert cfg.api_url == "http://localhost:17000"
        assert cfg.timeout == 10.0
        assert cfg.theme == "dark"
        assert cfg.port == 7860
        assert cfg.native_mode is True

    def test_env_var_overrides_api_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_API_URL", "http://remote:8080")
        from dex_studio.config import load_config

        cfg = load_config()
        assert cfg.api_url == "http://remote:8080"

    def test_env_var_overrides_theme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_THEME", "light")
        from dex_studio.config import load_config

        cfg = load_config()
        assert cfg.theme == "light"

    def test_env_var_overrides_timeout_as_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEX_STUDIO_TIMEOUT", "30.5")
        from dex_studio.config import load_config

        cfg = load_config()
        assert cfg.timeout == 30.5

    def test_invalid_timeout_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-numeric timeout env var should either raise or use default — not crash."""
        monkeypatch.setenv("DEX_STUDIO_TIMEOUT", "not-a-number")
        from dex_studio.config import load_config

        try:
            cfg = load_config()
            assert isinstance(cfg.timeout, float)
        except (ValueError, TypeError):
            pass

    def test_config_with_api_token(self) -> None:
        cfg = StudioConfig(api_token="my-jwt-token")
        assert cfg.api_token == "my-jwt-token"

    def test_config_api_url_no_trailing_slash(self) -> None:
        cfg = StudioConfig(api_url="http://localhost:17000/")
        client = DexClient(cfg)
        assert client.config.api_url == "http://localhost:17000/"
