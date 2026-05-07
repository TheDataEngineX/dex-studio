"""Tests for dex_studio.client module."""

from __future__ import annotations

import httpx
import pytest

from dex_studio.client import DexClient
from dex_studio.config import StudioConfig


@pytest.fixture()
def config() -> StudioConfig:
    return StudioConfig(api_url="http://localhost:9999", timeout=2.0)


class TestDexClientLifecycle:
    @pytest.mark.asyncio()
    async def test_connect_creates_client(self, config: StudioConfig) -> None:
        client = DexClient(config)
        await client.connect()
        assert client.is_connected
        await client.close()

    @pytest.mark.asyncio()
    async def test_ping_returns_true(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"status": "alive"}))
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        assert await client.ping() is True
        await client.close()


class TestDataEndpoints:
    @pytest.mark.asyncio()
    async def test_list_sources(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"sources": [], "count": 0})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.list_sources()
        assert "sources" in result
        await client.close()

    @pytest.mark.asyncio()
    async def test_run_pipeline(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"pipeline": "ingest", "success": True})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.run_pipeline("ingest")
        assert result["success"] is True
        await client.close()


class TestMLEndpoints:
    @pytest.mark.asyncio()
    async def test_list_experiments(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"experiments": [], "count": 0})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.list_experiments()
        assert "experiments" in result
        await client.close()

    @pytest.mark.asyncio()
    async def test_predict(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"model_name": "m", "prediction": 42})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.predict("m", {"x": 1.0})
        assert result["prediction"] == 42
        await client.close()


class TestAIEndpoints:
    @pytest.mark.asyncio()
    async def test_list_agents(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"agents": [], "count": 0})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.list_agents()
        assert "agents" in result
        await client.close()

    @pytest.mark.asyncio()
    async def test_agent_chat(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "agent": "bot",
                    "response": "Hi",
                    "iterations": 1,
                    "tool_calls": 0,
                },
            )
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.agent_chat("bot", "Hello")
        assert result["response"] == "Hi"
        await client.close()


class TestSystemEndpoints:
    @pytest.mark.asyncio()
    async def test_components(self, config: StudioConfig) -> None:
        client = DexClient(config)
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"components": []}))
        client._client = httpx.AsyncClient(transport=transport, base_url=config.api_url)
        result = await client.components()
        assert "components" in result
        await client.close()
