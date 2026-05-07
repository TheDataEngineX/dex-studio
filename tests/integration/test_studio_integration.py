"""Integration tests — StudioStore pub/sub, DexClient HTTP."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from dex_studio.client import DexAPIError, DexClient
from dex_studio.config import StudioConfig
from dex_studio.store import StudioStore

# ---------------------------------------------------------------------------
# StudioStore — pub/sub event bus
# ---------------------------------------------------------------------------


class TestStudioStore:
    def setup_method(self) -> None:
        self._store = StudioStore()

    def test_emit_triggers_listener(self) -> None:
        received: list[Any] = []
        self._store.on("test_event", received.append)
        self._store.emit("test_event", {"value": 42})
        assert len(received) == 1
        assert received[0]["value"] == 42

    def test_multiple_listeners_all_called(self) -> None:
        calls: list[str] = []
        self._store.on("evt", lambda p: calls.append("A"))
        self._store.on("evt", lambda p: calls.append("B"))
        self._store.emit("evt", {})
        assert set(calls) == {"A", "B"}

    def test_off_removes_listener(self) -> None:
        calls: list[Any] = []

        def handler(p: Any) -> None:
            calls.append(p)

        self._store.on("evt", handler)
        self._store.off("evt", handler)
        self._store.emit("evt", "payload")
        assert calls == []

    def test_emit_unknown_event_is_noop(self) -> None:
        # No listeners — should not raise
        self._store.emit("unknown_event", {"key": "value"})

    def test_broken_listener_does_not_crash_store(self) -> None:
        def bad_handler(p: Any) -> None:
            raise RuntimeError("boom")

        calls: list[Any] = []
        self._store.on("evt", bad_handler)
        self._store.on("evt", calls.append)
        self._store.emit("evt", "data")
        # Second listener should still be called despite first failing
        assert calls == ["data"]

    def test_emit_no_payload(self) -> None:
        received: list[Any] = []
        self._store.on("ping", received.append)
        self._store.emit("ping")
        assert len(received) == 1
        assert received[0] is None


# ---------------------------------------------------------------------------
# StudioStore — pipeline status tracking
# ---------------------------------------------------------------------------


class TestStudioStorePipelineStatus:
    def setup_method(self) -> None:
        self._store = StudioStore()

    def test_set_pipeline_status_updates_state(self) -> None:
        self._store.set_pipeline_status("ingest-users", "running")
        assert self._store.pipeline_runs["ingest-users"] == "running"

    def test_set_pipeline_status_emits_event(self) -> None:
        events: list[Any] = []
        self._store.on("pipeline_run", events.append)
        self._store.set_pipeline_status("ingest-events", "success")
        assert len(events) == 1
        assert events[0]["name"] == "ingest-events"
        assert events[0]["status"] == "success"

    def test_success_creates_positive_notification(self) -> None:
        self._store.set_pipeline_status("ingest-jobs", "success")
        assert self._store.unread_count() > 0
        notif = list(self._store.notifications)[0]
        assert "ingest-jobs" in notif.message
        assert notif.type == "positive"

    def test_failure_creates_negative_notification(self) -> None:
        self._store.set_pipeline_status("failing-pipe", "failure")
        notif = list(self._store.notifications)[0]
        assert notif.type == "negative"

    def test_running_status_no_notification(self) -> None:
        self._store.set_pipeline_status("live-pipe", "running")
        assert self._store.unread_count() == 0

    def test_multiple_pipelines_tracked_independently(self) -> None:
        self._store.set_pipeline_status("pipe-a", "success")
        self._store.set_pipeline_status("pipe-b", "running")
        self._store.set_pipeline_status("pipe-c", "failure")
        assert self._store.pipeline_runs["pipe-a"] == "success"
        assert self._store.pipeline_runs["pipe-b"] == "running"
        assert self._store.pipeline_runs["pipe-c"] == "failure"


# ---------------------------------------------------------------------------
# StudioStore — notifications
# ---------------------------------------------------------------------------


class TestStudioStoreNotifications:
    def setup_method(self) -> None:
        self._store = StudioStore()

    def test_notify_adds_to_queue(self) -> None:
        self._store.notify("Pipeline completed", type="info")
        assert self._store.unread_count() == 1

    def test_notify_emits_notification_event(self) -> None:
        events: list[Any] = []
        self._store.on("notification", events.append)
        self._store.notify("Done!", type="success", route="/data/pipelines")
        assert len(events) == 1
        assert events[0]["message"] == "Done!"

    def test_mark_all_read_clears_unread_count(self) -> None:
        self._store.notify("Msg 1")
        self._store.notify("Msg 2")
        self._store.notify("Msg 3")
        assert self._store.unread_count() == 3
        self._store.mark_all_read()
        assert self._store.unread_count() == 0

    def test_mark_all_read_emits_event(self) -> None:
        events: list[Any] = []
        self._store.on("notifications_read", events.append)
        self._store.mark_all_read()
        assert len(events) == 1

    def test_notifications_capped_at_100(self) -> None:
        for i in range(110):
            self._store.notify(f"Msg {i}")
        assert len(self._store.notifications) == 100

    def test_newest_notification_at_front(self) -> None:
        self._store.notify("First")
        self._store.notify("Second")
        front = list(self._store.notifications)[0]
        assert front.message == "Second"


# ---------------------------------------------------------------------------
# DexClient — with mock HTTP transport
# ---------------------------------------------------------------------------


def _mock_transport(responses: dict[str, Any]) -> httpx.MockTransport:
    """Build a MockTransport that returns pre-configured JSON responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in responses:
            data = responses[path]
            if isinstance(data, int):
                return httpx.Response(data)
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


class TestDexClientWithMock:
    def _config(self) -> StudioConfig:
        return StudioConfig(api_url="http://dex.local", timeout=5.0)

    @pytest.mark.asyncio
    async def test_ping_healthy_returns_true(self) -> None:
        transport = _mock_transport({"/api/v1/health": {"status": "healthy"}})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        result = await client.ping()
        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_ping_unhealthy_returns_false(self) -> None:
        transport = _mock_transport({"/api/v1/health": 503})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        result = await client.ping()
        assert result is False
        await client.close()

    @pytest.mark.asyncio
    async def test_health_returns_dict(self) -> None:
        transport = _mock_transport({"/api/v1/health": {"status": "healthy", "version": "1.2.3"}})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.health()
        assert data["status"] == "healthy"
        assert data["version"] == "1.2.3"
        await client.close()

    @pytest.mark.asyncio
    async def test_list_pipelines_returns_dict(self) -> None:
        payload = {"count": 3, "pipelines": [{"name": "p1"}, {"name": "p2"}, {"name": "p3"}]}
        transport = _mock_transport({"/api/v1/pipelines/": payload})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.list_pipelines()
        assert data["count"] == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_list_experiments_returns_dict(self) -> None:
        payload = {"count": 2, "experiments": [{"id": "e1"}, {"id": "e2"}]}
        transport = _mock_transport({"/api/v1/ml/experiments": payload})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.list_experiments()
        assert data["count"] == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_list_agents_returns_dict(self) -> None:
        payload = {"count": 1, "agents": [{"name": "assistant"}]}
        transport = _mock_transport({"/api/v1/ai/agents": payload})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.list_agents()
        assert data["count"] == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_api_error_on_404(self) -> None:
        transport = _mock_transport({})  # all paths → 404
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        with pytest.raises(DexAPIError) as exc_info:
            await client.health()
        assert exc_info.value.status_code == 404
        await client.close()

    @pytest.mark.asyncio
    async def test_is_connected_after_connect(self) -> None:
        config = self._config()
        client = DexClient(config=config)
        assert not client.is_connected
        await client.connect()
        assert client.is_connected
        await client.close()

    @pytest.mark.asyncio
    async def test_get_raises_if_not_connected(self) -> None:
        config = self._config()
        client = DexClient(config=config)
        with pytest.raises(RuntimeError, match="not connected"):
            await client.health()

    @pytest.mark.asyncio
    async def test_list_tools_returns_dict(self) -> None:
        payload = {
            "count": 3,
            "tools": [{"name": "echo"}, {"name": "query"}, {"name": "list_tools"}],
        }
        transport = _mock_transport({"/api/v1/ai/tools": payload})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.list_tools()
        assert data["count"] == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_warehouse_layers_returns_dict(self) -> None:
        payload = {"layers": [{"name": "bronze"}, {"name": "silver"}, {"name": "gold"}]}
        transport = _mock_transport({"/api/v1/data/warehouse/layers": payload})
        config = self._config()
        client = DexClient(config=config)
        client._client = httpx.AsyncClient(base_url=config.api_url, transport=transport)
        data = await client.warehouse_layers()
        assert len(data["layers"]) == 3
        await client.close()


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestStudioConfig:
    def test_default_config_has_localhost_url(self) -> None:
        from dex_studio.config import load_config

        cfg = load_config()
        assert "localhost" in cfg.api_url or "17000" in cfg.api_url

    def test_custom_api_url(self) -> None:
        cfg = StudioConfig(api_url="http://my-dex.internal:17000", timeout=10.0)
        assert cfg.api_url == "http://my-dex.internal:17000"
        assert cfg.timeout == 10.0

    def test_config_with_token(self) -> None:
        cfg = StudioConfig(api_url="http://localhost:17000", api_token="secret-token")
        assert cfg.api_token == "secret-token"
