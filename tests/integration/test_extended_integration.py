"""Extended integration tests for edge cases and untested modules."""

from __future__ import annotations

import httpx
import pytest

from dex_studio.client import DexAPIError, DexClient
from dex_studio.config import StudioConfig
from dex_studio.store import StudioStore
from dex_studio.theme import COLORS

# ---------------------------------------------------------------------------
# dex_studio.client — edge cases
# ---------------------------------------------------------------------------


class TestDexClientEdgeCases:
    @pytest.fixture()
    def client(self) -> DexClient:
        cfg = StudioConfig(api_url="http://localhost:9999", timeout=2.0)
        return DexClient(cfg)

    @pytest.mark.asyncio()
    async def test_connect_error_raises_dex_api_error(self, client: DexClient) -> None:
        """Connection errors should raise DexAPIError."""
        # Use a non-routable address to trigger connection error
        # TEST-NET-1 (RFC 5737) — non-routable address
        bad_config = StudioConfig(api_url="http://192.0.2.1:9999", timeout=1.0)
        bad_client = DexClient(bad_config)
        await bad_client.connect()
        with pytest.raises(DexAPIError):
            await bad_client.health()
        await bad_client.close()

    @pytest.mark.asyncio()
    async def test_malformed_json_raises_dex_api_error(self, client: DexClient) -> None:
        """Non-JSON response body should raise DexAPIError."""
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"not json"))
        client._client = httpx.AsyncClient(transport=transport, base_url=client.config.api_url)
        with pytest.raises(DexAPIError):
            await client.health()
        await client.close()

    @pytest.mark.asyncio()
    async def test_500_error_raises_dex_api_error(self, client: DexClient) -> None:
        transport = httpx.MockTransport(lambda req: httpx.Response(500, json={"detail": "boom"}))
        client._client = httpx.AsyncClient(transport=transport, base_url=client.config.api_url)
        with pytest.raises(DexAPIError) as exc_info:
            await client.health()
        assert exc_info.value.status_code == 500
        await client.close()

    @pytest.mark.asyncio()
    async def test_404_error_raises_dex_api_error(self, client: DexClient) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(404, json={"detail": "not found"})
        )
        client._client = httpx.AsyncClient(transport=transport, base_url=client.config.api_url)
        with pytest.raises(DexAPIError) as exc_info:
            await client.health()
        assert exc_info.value.status_code == 404
        await client.close()

    @pytest.mark.asyncio()
    async def test_close_idempotent(self, client: DexClient) -> None:
        """Calling close multiple times should not raise."""
        await client.connect()
        await client.close()
        await client.close()  # second call should not raise

    @pytest.mark.asyncio()
    async def test_get_with_query_params(self, client: DexClient) -> None:
        captured: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(str(req.url))
            return httpx.Response(200, json={"logs": [], "count": 0})

        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=client.config.api_url
        )
        await client.logs(level="error", limit=50)
        assert "level=error" in captured[0]
        assert "limit=50" in captured[0]
        await client.close()

    @pytest.mark.asyncio()
    async def test_post_with_json_body(self, client: DexClient) -> None:
        captured: list[bytes] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req.content)
            return httpx.Response(200, json={"reply": "hi"})

        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url=client.config.api_url
        )
        await client.agent_chat("bot", "hello")
        assert b"hello" in captured[0]
        await client.close()


# ---------------------------------------------------------------------------
# dex_studio.theme — edge cases
# ---------------------------------------------------------------------------


class TestThemeEdgeCases:
    def test_all_required_keys_present(self) -> None:
        required = [
            "bg_primary",
            "bg_secondary",
            "bg_sidebar",
            "bg_hover",
            "accent",
            "accent_light",
            "text_primary",
            "text_muted",
            "text_dim",
            "text_faint",
            "border",
            "success",
            "warning",
            "error",
        ]
        for key in required:
            assert key in COLORS, f"Missing key: {key}"

    def test_no_empty_color_values(self) -> None:
        for key, value in COLORS.items():
            assert value != "", f"Empty color for {key}"

    def test_colors_are_valid_hex(self) -> None:
        import re

        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for key, value in COLORS.items():
            assert hex_pattern.match(value), f"Invalid hex color for {key}: {value}"

    def test_bg_primary_is_dark(self) -> None:
        """Dark mode: primary background should be dark (low hex value)."""
        hex_val = COLORS["bg_primary"].lstrip("#")
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        assert brightness < 128, "bg_primary should be dark for dark mode"

    def test_accent_is_colorful(self) -> None:
        """Accent should be a saturated color (not gray)."""
        hex_val = COLORS["accent"].lstrip("#")
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        assert max_val - min_val > 50, "accent should be a colorful (non-gray) value"


# ---------------------------------------------------------------------------
# StudioStore — edge cases
# ---------------------------------------------------------------------------


class TestStudioStoreEdgeCases:
    def setup_method(self) -> None:
        self.store = StudioStore()

    def test_emit_same_event_multiple_listeners(self) -> None:
        results: list[int] = []
        self.store.on("evt", lambda p: results.append(1))
        self.store.on("evt", lambda p: results.append(2))
        self.store.on("evt", lambda p: results.append(3))
        self.store.emit("evt", {})
        assert sum(results) == 6  # 1+2+3

    def test_off_removes_only_target_handler(self) -> None:
        results: list[str] = []

        def h1(p: object) -> None:
            results.append("a")

        def h2(p: object) -> None:
            results.append("b")

        self.store.on("evt", h1)
        self.store.on("evt", h2)
        self.store.off("evt", h1)
        self.store.emit("evt", {})
        assert results == ["b"]

    def test_notify_multiple_types(self) -> None:
        self.store.notify("Info", type="info")
        self.store.notify("Success", type="success")
        self.store.notify("Warning", type="warning")
        self.store.notify("Error", type="error")
        assert self.store.unread_count() == 4

    def test_mark_all_read_idempotent(self) -> None:
        self.store.notify("Msg")
        assert self.store.unread_count() == 1
        self.store.mark_all_read()
        assert self.store.unread_count() == 0
        self.store.mark_all_read()  # should not raise
        assert self.store.unread_count() == 0

    def test_set_pipeline_status_updates_existing(self) -> None:
        self.store.set_pipeline_status("pipe", "running")
        assert self.store.pipeline_runs["pipe"] == "running"
        self.store.set_pipeline_status("pipe", "success")
        assert self.store.pipeline_runs["pipe"] == "success"

    def test_notification_message_truncation_not_applied(self) -> None:
        long_msg = "x" * 500
        self.store.notify(long_msg)
        notif = list(self.store.notifications)[0]
        assert len(notif.message) == 500
