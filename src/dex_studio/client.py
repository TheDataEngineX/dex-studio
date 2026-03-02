"""HTTP client for the DEX engine API.

Wraps ``httpx.AsyncClient`` with retry logic, timeout handling, and
structured error responses.  All public methods return typed dicts or
raise ``DexAPIError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx

from dex_studio.config import StudioConfig

__all__ = [
    "DexAPIError",
    "DexClient",
]


class DexAPIError(Exception):
    """Raised when a DEX engine API call fails."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"DEX API error {status_code} ({url}): {message}")


@dataclass(slots=True)
class DexClient:
    """Async HTTP client for the DEX engine REST API.

    Usage::

        client = DexClient(config)
        await client.connect()
        health = await client.health()
        await client.close()
    """

    config: StudioConfig
    _client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the underlying ``httpx.AsyncClient``."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"

        self._client = httpx.AsyncClient(
            base_url=self.config.api_url,
            timeout=httpx.Timeout(self.config.timeout),
            headers=headers,
        )

    async def close(self) -> None:
        """Shut down the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and not self._client.is_closed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        """Issue a GET and return parsed JSON, raising ``DexAPIError`` on failure."""
        if self._client is None:
            msg = "Client not connected — call connect() first"
            raise RuntimeError(msg)

        try:
            resp = await self._client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise DexAPIError(
                status_code=0,
                message=f"Connection failed: {exc}",
                url=f"{self.config.api_url}{path}",
            ) from exc

        if resp.status_code >= 400:
            body = resp.text[:500]
            raise DexAPIError(
                status_code=resp.status_code,
                message=body,
                url=str(resp.url),
            )
        return cast(dict[str, Any], resp.json())

    async def _post(self, path: str, json: Any = None) -> dict[str, Any]:
        """Issue a POST and return parsed JSON."""
        if self._client is None:
            msg = "Client not connected — call connect() first"
            raise RuntimeError(msg)

        try:
            resp = await self._client.post(path, json=json)
        except httpx.HTTPError as exc:
            raise DexAPIError(
                status_code=0,
                message=f"Connection failed: {exc}",
                url=f"{self.config.api_url}{path}",
            ) from exc

        if resp.status_code >= 400:
            body = resp.text[:500]
            raise DexAPIError(
                status_code=resp.status_code,
                message=body,
                url=str(resp.url),
            )
        return cast(dict[str, Any], resp.json())

    # ------------------------------------------------------------------
    # Health & System
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """``GET /health``"""
        return await self._get("/health")

    async def readiness(self) -> dict[str, Any]:
        """``GET /ready``"""
        return await self._get("/ready")

    async def startup(self) -> dict[str, Any]:
        """``GET /startup``"""
        return await self._get("/startup")

    async def system_config(self) -> dict[str, Any]:
        """``GET /api/v1/system/config``"""
        return await self._get("/api/v1/system/config")

    async def root(self) -> dict[str, Any]:
        """``GET /`` — returns API name + version."""
        return await self._get("/")

    # ------------------------------------------------------------------
    # Data Quality
    # ------------------------------------------------------------------

    async def data_sources(self, cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        """``GET /api/v1/data/sources``"""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._get("/api/v1/data/sources", **params)

    async def data_quality_summary(self) -> dict[str, Any]:
        """``GET /api/v1/data/quality``"""
        return await self._get("/api/v1/data/quality")

    async def data_quality_layer(self, layer: str, limit: int = 10) -> dict[str, Any]:
        """``GET /api/v1/data/quality/{layer}``"""
        return await self._get(f"/api/v1/data/quality/{layer}", limit=limit)

    # ------------------------------------------------------------------
    # Warehouse / Lineage
    # ------------------------------------------------------------------

    async def warehouse_layers(self) -> dict[str, Any]:
        """``GET /api/v1/warehouse/layers``"""
        return await self._get("/api/v1/warehouse/layers")

    async def lineage(self, event_id: str) -> dict[str, Any]:
        """``GET /api/v1/warehouse/lineage/{event_id}``"""
        return await self._get(f"/api/v1/warehouse/lineage/{event_id}")

    # ------------------------------------------------------------------
    # ML (requires ML router mounted on DEX engine)
    # ------------------------------------------------------------------

    async def list_models(self) -> dict[str, Any]:
        """``GET /api/v1/models``"""
        return await self._get("/api/v1/models")

    async def model_metadata(self, name: str, version: str | None = None) -> dict[str, Any]:
        """``GET /api/v1/models/{name}``"""
        params: dict[str, Any] = {}
        if version:
            params["version"] = version
        return await self._get(f"/api/v1/models/{name}", **params)

    async def predict(
        self,
        model_name: str,
        features: list[dict[str, Any]],
        *,
        version: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """``POST /api/v1/predict``"""
        payload: dict[str, Any] = {
            "model_name": model_name,
            "features": features,
        }
        if version:
            payload["version"] = version
        if request_id:
            payload["request_id"] = request_id
        return await self._post("/api/v1/predict", json=payload)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return ``True`` if DEX engine is reachable and healthy."""
        try:
            result = await self.health()
            return result.get("status") == "alive"
        except (DexAPIError, RuntimeError):
            return False
