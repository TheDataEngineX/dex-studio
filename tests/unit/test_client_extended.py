"""Extended tests for DexClient — error handling, auth headers, all endpoints.

Complements test_client.py with DexAPIError propagation, timeout,
auth header injection, 4xx/5xx handling, and all API method coverage.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from dex_studio.client import DexAPIError, DexClient
from dex_studio.config import StudioConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> StudioConfig:
    return StudioConfig(api_url="http://localhost:9999", timeout=2.0)


@pytest.fixture()
def config_with_token() -> StudioConfig:
    return StudioConfig(
        api_url="http://localhost:9999", timeout=2.0, api_token="Bearer test-token-123"
    )


def _mock_client(config: StudioConfig, response: httpx.Response) -> DexClient:
    client = DexClient(config)
    transport = httpx.MockTransport(lambda req: response)
    client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
    return client


def _mock_client_fn(config: StudioConfig, handler: Any) -> DexClient:
    client = DexClient(config)
    transport = httpx.MockTransport(handler)
    client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
    return client


# ---------------------------------------------------------------------------
# DexAPIError
# ---------------------------------------------------------------------------


class TestDexAPIError:
    def test_message_format(self) -> None:
        err = DexAPIError(404, "not found", "http://example.com/api")
        assert "404" in str(err)
        assert "not found" in str(err)
        assert "http://example.com/api" in str(err)

    def test_attributes(self) -> None:
        err = DexAPIError(503, "service down", "http://x.com")
        assert err.status_code == 503
        assert err.url == "http://x.com"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio()
    async def test_not_connected_before_connect(self, config: StudioConfig) -> None:
        client = DexClient(config)
        assert not client.is_connected

    @pytest.mark.asyncio()
    async def test_connected_after_connect(self, config: StudioConfig) -> None:
        client = DexClient(config)
        await client.connect()
        assert client.is_connected
        await client.close()

    @pytest.mark.asyncio()
    async def test_not_connected_after_close(self, config: StudioConfig) -> None:
        client = DexClient(config)
        await client.connect()
        await client.close()
        assert not client.is_connected

    @pytest.mark.asyncio()
    async def test_close_without_connect_does_not_raise(self, config: StudioConfig) -> None:
        client = DexClient(config)
        await client.close()  # must not raise

    @pytest.mark.asyncio()
    async def test_get_raises_when_not_connected(self, config: StudioConfig) -> None:
        client = DexClient(config)
        with pytest.raises(RuntimeError, match="not connected"):
            await client._get("/anything")

    @pytest.mark.asyncio()
    async def test_post_raises_when_not_connected(self, config: StudioConfig) -> None:
        client = DexClient(config)
        with pytest.raises(RuntimeError, match="not connected"):
            await client._post("/anything")


# ---------------------------------------------------------------------------
# Auth header injection
# ---------------------------------------------------------------------------


class TestAuthHeaderInjection:
    @pytest.mark.asyncio()
    async def test_bearer_token_sent_in_header(self, config_with_token: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"status": "alive"})

        client = DexClient(config_with_token)
        await client.connect()
        # Replace transport after connect to capture real headers
        transport = httpx.MockTransport(handler)
        assert client._client is not None
        client._client._transport = transport  # type: ignore[attr-defined]
        await client.ping()
        await client.close()

        assert len(captured) == 1
        auth = captured[0].headers.get("authorization", "")
        assert "Bearer test-token-123" in auth

    @pytest.mark.asyncio()
    async def test_no_auth_header_without_token(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"status": "alive"})

        client = DexClient(config)
        await client.connect()
        transport = httpx.MockTransport(handler)
        assert client._client is not None
        client._client._transport = transport  # type: ignore[attr-defined]
        await client.ping()
        await client.close()

        assert "authorization" not in captured[0].headers


# ---------------------------------------------------------------------------
# Error propagation — 4xx / 5xx raise DexAPIError
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    @pytest.mark.asyncio()
    async def test_404_raises_dex_api_error(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(404, text="not found"))
        with pytest.raises(DexAPIError) as exc_info:
            await client._get("/api/v1/pipelines/missing")
        assert exc_info.value.status_code == 404
        await client.close()

    @pytest.mark.asyncio()
    async def test_500_raises_dex_api_error(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(500, text="internal error"))
        with pytest.raises(DexAPIError) as exc_info:
            await client._get("/api/v1/health")
        assert exc_info.value.status_code == 500
        await client.close()

    @pytest.mark.asyncio()
    async def test_503_raises_dex_api_error(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(503, text="service unavailable"))
        with pytest.raises(DexAPIError) as exc_info:
            await client._post("/api/v1/ai/agents/bot/chat")
        assert exc_info.value.status_code == 503
        await client.close()

    @pytest.mark.asyncio()
    async def test_200_does_not_raise(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(200, json={"ok": True}))
        result = await client._get("/ok")
        assert result["ok"] is True
        await client.close()

    @pytest.mark.asyncio()
    async def test_error_message_truncated_to_500_chars(self, config: StudioConfig) -> None:
        long_body = "x" * 1000
        client = _mock_client(config, httpx.Response(400, text=long_body))
        with pytest.raises(DexAPIError) as exc_info:
            await client._get("/api/v1/bad")
        # The error message in DexAPIError is truncated to 500
        assert len(exc_info.value.args[0]) < 600
        await client.close()


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    @pytest.mark.asyncio()
    async def test_ping_true_for_alive(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(200, json={"status": "alive"}))
        assert await client.ping() is True
        await client.close()

    @pytest.mark.asyncio()
    async def test_ping_true_for_healthy(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(200, json={"status": "healthy"}))
        assert await client.ping() is True
        await client.close()

    @pytest.mark.asyncio()
    async def test_ping_false_for_unknown_status(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(200, json={"status": "degraded"}))
        assert await client.ping() is False
        await client.close()

    @pytest.mark.asyncio()
    async def test_ping_false_on_connection_error(self, config: StudioConfig) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = _mock_client_fn(config, handler)
        assert await client.ping() is False
        await client.close()

    @pytest.mark.asyncio()
    async def test_ping_false_on_api_error(self, config: StudioConfig) -> None:
        client = _mock_client(config, httpx.Response(503, text="down"))
        assert await client.ping() is False
        await client.close()


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------


class TestDataEndpoints:
    @pytest.mark.asyncio()
    async def test_get_source(self, config: StudioConfig) -> None:
        payload = {"name": "movies", "type": "csv", "path": "data.csv"}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.get_source("movies")
        assert result["name"] == "movies"
        await client.close()

    @pytest.mark.asyncio()
    async def test_get_pipeline(self, config: StudioConfig) -> None:
        payload = {"name": "ingest", "source": "movies", "transforms": 2}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.get_pipeline("ingest")
        assert result["name"] == "ingest"
        await client.close()

    @pytest.mark.asyncio()
    async def test_warehouse_layers(self, config: StudioConfig) -> None:
        payload = {"layers": [{"name": "bronze"}, {"name": "silver"}, {"name": "gold"}]}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.warehouse_layers()
        assert len(result["layers"]) == 3
        await client.close()

    @pytest.mark.asyncio()
    async def test_warehouse_tables(self, config: StudioConfig) -> None:
        payload = {"layer": "bronze", "tables": ["raw_jobs"], "count": 1}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.warehouse_tables("bronze")
        assert result["count"] == 1
        await client.close()

    @pytest.mark.asyncio()
    async def test_list_lineage(self, config: StudioConfig) -> None:
        payload = {"events": [], "count": 0}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.list_lineage()
        assert result["count"] == 0
        await client.close()

    @pytest.mark.asyncio()
    async def test_data_quality_summary(self, config: StudioConfig) -> None:
        payload = {"pipelines": [{"pipeline": "ingest", "has_quality_gate": True}]}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.data_quality_summary()
        assert "pipelines" in result
        await client.close()

    @pytest.mark.asyncio()
    async def test_data_quality_pipeline(self, config: StudioConfig) -> None:
        payload = {"pipeline": "ingest", "has_quality_gate": True}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.data_quality_pipeline("ingest")
        assert result["pipeline"] == "ingest"
        await client.close()


# ---------------------------------------------------------------------------
# ML endpoints
# ---------------------------------------------------------------------------


class TestMLEndpoints:
    @pytest.mark.asyncio()
    async def test_create_experiment(self, config: StudioConfig) -> None:
        payload = {"id": "exp-001", "name": "baseline"}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.create_experiment("baseline")
        assert result["name"] == "baseline"
        await client.close()

    @pytest.mark.asyncio()
    async def test_list_runs(self, config: StudioConfig) -> None:
        payload = {"experiment": "baseline", "runs": [], "count": 0}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.list_runs("baseline")
        assert result["count"] == 0
        await client.close()

    @pytest.mark.asyncio()
    async def test_get_model(self, config: StudioConfig) -> None:
        payload = {"name": "classifier", "version": "1.0", "stage": "production"}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.get_model("classifier")
        assert result["stage"] == "production"
        await client.close()

    @pytest.mark.asyncio()
    async def test_promote_model(self, config: StudioConfig) -> None:
        payload = {"name": "clf", "version": "2", "stage": "staging", "promoted": True}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.promote_model("clf", "staging")
        assert result["promoted"] is True
        await client.close()

    @pytest.mark.asyncio()
    async def test_list_feature_groups(self, config: StudioConfig) -> None:
        payload = {"groups": ["user_features"], "count": 1}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.list_feature_groups()
        assert result["count"] == 1
        await client.close()

    @pytest.mark.asyncio()
    async def test_get_features_with_entity_ids(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"feature_group": "users", "features": []})

        client = _mock_client_fn(config, handler)
        await client.get_features("users", entity_ids=["u1", "u2"])
        await client.close()
        # httpx URL-encodes commas as %2C — check both forms
        url_str = str(captured[0].url)
        assert "u1" in url_str and "u2" in url_str

    @pytest.mark.asyncio()
    async def test_save_features(self, config: StudioConfig) -> None:
        payload = {"feature_group": "users", "saved": 2}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.save_features(
            "users", [{"id": "u1", "score": 0.9}, {"id": "u2", "score": 0.7}], "id"
        )
        assert result["saved"] == 2
        await client.close()

    @pytest.mark.asyncio()
    async def test_check_drift(self, config: StudioConfig) -> None:
        payload = {"pipeline": "ingest", "status": "ok", "reports": []}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.check_drift("ingest")
        assert result["status"] == "ok"
        await client.close()


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------


class TestAIEndpoints:
    @pytest.mark.asyncio()
    async def test_list_agents(self, config: StudioConfig) -> None:
        payload = {"agents": [{"name": "data-analyst"}], "count": 1}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.list_agents()
        assert result["count"] == 1
        await client.close()

    @pytest.mark.asyncio()
    async def test_get_agent(self, config: StudioConfig) -> None:
        payload = {"name": "data-analyst", "runtime": "builtin", "tools": ["query"]}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.get_agent("data-analyst")
        assert result["runtime"] == "builtin"
        await client.close()

    @pytest.mark.asyncio()
    async def test_agent_chat(self, config: StudioConfig) -> None:
        payload = {"agent": "data-analyst", "response": "42", "iterations": 1, "tool_calls": 0}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.agent_chat("data-analyst", "What is 6*7?")
        assert result["response"] == "42"
        await client.close()

    @pytest.mark.asyncio()
    async def test_agent_chat_posts_to_correct_path(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(
                200, json={"agent": "bot", "response": "ok", "iterations": 1, "tool_calls": 0}
            )

        client = _mock_client_fn(config, handler)
        await client.agent_chat("bot", "hello")
        await client.close()
        assert "/ai/agents/bot/chat" in str(captured[0].url)

    @pytest.mark.asyncio()
    async def test_list_tools(self, config: StudioConfig) -> None:
        payload = {"tools": [{"name": "query", "description": "SQL"}], "count": 1}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.list_tools()
        assert result["count"] == 1
        await client.close()

    @pytest.mark.asyncio()
    async def test_get_tool(self, config: StudioConfig) -> None:
        payload = {"name": "query", "description": "SQL", "parameters": {}}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.get_tool("query")
        assert result["name"] == "query"
        await client.close()


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


class TestSystemEndpoints:
    @pytest.mark.asyncio()
    async def test_components(self, config: StudioConfig) -> None:
        payload = {"components": [{"name": "tracker", "status": "ok"}]}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.components()
        assert "components" in result
        await client.close()

    @pytest.mark.asyncio()
    async def test_logs_with_level_filter(self, config: StudioConfig) -> None:
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"logs": [], "count": 0, "message": ""})

        client = _mock_client_fn(config, handler)
        await client.logs(level="error", limit=50)
        await client.close()
        assert "level=error" in str(captured[0].url)
        assert "limit=50" in str(captured[0].url)

    @pytest.mark.asyncio()
    async def test_traces(self, config: StudioConfig) -> None:
        payload = {"traces": [], "count": 0}
        client = _mock_client(config, httpx.Response(200, json=payload))
        result = await client.traces(limit=10)
        assert "traces" in result
        await client.close()
