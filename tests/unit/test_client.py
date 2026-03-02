"""Tests for dex_studio.client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from dex_studio.client import DexAPIError, DexClient
from dex_studio.config import StudioConfig


@pytest.fixture()
def client_config() -> StudioConfig:
    return StudioConfig(api_url="http://testhost:8000", timeout=2.0)


class TestDexClient:
    """Tests for the DexClient class."""

    async def test_connect_creates_client(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        assert not client.is_connected
        await client.connect()
        assert client.is_connected
        await client.close()
        assert not client.is_connected

    async def test_get_raises_when_not_connected(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        with pytest.raises(RuntimeError, match="not connected"):
            await client._get("/health")

    async def test_ping_returns_true_on_alive(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        await client.connect()
        mock_response = httpx.Response(200, json={"status": "alive"})
        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            assert await client.ping() is True
        await client.close()

    async def test_ping_returns_false_on_error(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        await client.connect()
        with patch.object(
            client._client,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("refused"),
        ):
            assert await client.ping() is False
        await client.close()

    async def test_get_raises_dex_api_error_on_4xx(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        await client.connect()
        mock_response = httpx.Response(
            404,
            json={"error": "not_found"},
            request=httpx.Request("GET", "http://testhost:8000/bad"),
        )
        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(DexAPIError) as exc_info:
                await client._get("/bad")
            assert exc_info.value.status_code == 404
        await client.close()

    async def test_health_endpoint(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        await client.connect()
        mock_response = httpx.Response(200, json={"status": "alive"})
        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.health()
            assert result == {"status": "alive"}
        await client.close()

    async def test_auth_header_included(self) -> None:
        cfg = StudioConfig(api_url="http://test:8000", api_token="my-token")
        client = DexClient(config=cfg)
        await client.connect()
        assert client._client is not None
        assert client._client.headers["Authorization"] == "Bearer my-token"
        await client.close()

    async def test_data_sources_passes_params(self, client_config: StudioConfig) -> None:
        client = DexClient(config=client_config)
        await client.connect()
        mock_response = httpx.Response(
            200, json={"items": [], "next_cursor": None}
        )
        with patch.object(
            client._client, "get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_get:
            await client.data_sources(cursor="abc", limit=5)
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args
            assert call_kwargs[1]["params"]["cursor"] == "abc"
            assert call_kwargs[1]["params"]["limit"] == 5
        await client.close()


class TestDexAPIError:
    """Tests for the DexAPIError exception."""

    def test_message_format(self) -> None:
        err = DexAPIError(status_code=500, message="boom", url="http://x/health")
        assert "500" in str(err)
        assert "boom" in str(err)
        assert "http://x/health" in str(err)

    def test_attributes(self) -> None:
        err = DexAPIError(status_code=404, message="not found", url="/api/v1/models")
        assert err.status_code == 404
        assert err.url == "/api/v1/models"
