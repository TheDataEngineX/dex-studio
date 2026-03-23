"""HTTP client wrapper for DEX engine API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from dex_studio.config import StudioConfig

logger = logging.getLogger(__name__)

__all__ = ["DexAPIError", "DexClient"]


class DexAPIError(Exception):
    """Raised when the DEX engine returns an error response."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} from {url}: {message}")


@dataclass(slots=True)
class DexClient:
    """Async HTTP client for the DEX engine API."""

    config: StudioConfig
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    async def connect(self) -> None:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        self._client = httpx.AsyncClient(
            base_url=self.config.api_url,
            timeout=self.config.timeout,
            headers=headers,
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and not self._client.is_closed

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Client not connected -- call connect() first")
        resp = await self._client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        if resp.status_code >= 400:
            raise DexAPIError(resp.status_code, resp.text[:500], str(resp.url))
        return resp.json()  # type: ignore[no-any-return]

    async def _post(self, path: str, json: Any = None) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Client not connected -- call connect() first")
        resp = await self._client.post(path, json=json)
        if resp.status_code >= 400:
            raise DexAPIError(resp.status_code, resp.text[:500], str(resp.url))
        return resp.json()  # type: ignore[no-any-return]

    # --- Health ---
    async def ping(self) -> bool:
        try:
            data = await self._get("/api/v1/health")
            return data.get("status") in ("alive", "healthy")
        except (DexAPIError, RuntimeError, httpx.HTTPError):
            return False

    async def health(self) -> dict[str, Any]:
        return await self._get("/api/v1/health")

    async def root(self) -> dict[str, Any]:
        return await self._get("/")

    # --- Data ---
    async def list_sources(self) -> dict[str, Any]:
        return await self._get("/api/v1/data/sources")

    async def get_source(self, name: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/data/sources/{name}")

    async def list_pipelines(self) -> dict[str, Any]:
        return await self._get("/api/v1/pipelines/")

    async def get_pipeline(self, name: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/pipelines/{name}")

    async def run_pipeline(self, name: str) -> dict[str, Any]:
        return await self._post(f"/api/v1/pipelines/{name}/run")

    async def warehouse_layers(self) -> dict[str, Any]:
        return await self._get("/api/v1/data/warehouse/layers")

    async def warehouse_tables(self, layer: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/data/warehouse/layers/{layer}/tables")

    async def list_lineage(self) -> dict[str, Any]:
        return await self._get("/api/v1/data/lineage")

    async def get_lineage_event(self, event_id: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/data/lineage/{event_id}")

    async def data_quality_summary(self) -> dict[str, Any]:
        return await self._get("/api/v1/data/quality/summary")

    async def data_quality_pipeline(self, pipeline: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/data/quality/{pipeline}")

    # --- ML ---
    async def list_experiments(self) -> dict[str, Any]:
        return await self._get("/api/v1/ml/experiments")

    async def create_experiment(self, name: str) -> dict[str, Any]:
        return await self._post(f"/api/v1/ml/experiments/{name}")

    async def list_runs(self, experiment: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/ml/experiments/{experiment}/runs")

    async def list_models(self) -> dict[str, Any]:
        return await self._get("/api/v1/ml/models")

    async def get_model(self, name: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/ml/models/{name}")

    async def promote_model(self, name: str, stage: str) -> dict[str, Any]:
        return await self._post(f"/api/v1/ml/models/{name}/promote", json={"stage": stage})

    async def predict(self, model_name: str, features: dict[str, Any]) -> dict[str, Any]:
        return await self._post(
            "/api/v1/ml/predictions",
            json={"model_name": model_name, "features": features},
        )

    async def list_feature_groups(self) -> dict[str, Any]:
        return await self._get("/api/v1/ml/features")

    async def get_features(self, group: str, entity_ids: list[str] | None = None) -> dict[str, Any]:
        ids = ",".join(entity_ids) if entity_ids else None
        return await self._get(f"/api/v1/ml/features/{group}", entity_ids=ids)

    async def save_features(
        self, group: str, data: list[dict[str, Any]], entity_key: str
    ) -> dict[str, Any]:
        return await self._post(
            f"/api/v1/ml/features/{group}",
            json={"entity_key": entity_key, "data": data},
        )

    async def check_drift(self, pipeline: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/ml/drift/{pipeline}")

    # --- AI ---
    async def list_agents(self) -> dict[str, Any]:
        return await self._get("/api/v1/ai/agents")

    async def get_agent(self, name: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/ai/agents/{name}")

    async def agent_chat(self, name: str, message: str) -> dict[str, Any]:
        return await self._post(f"/api/v1/ai/agents/{name}/chat", json={"message": message})

    async def list_tools(self) -> dict[str, Any]:
        return await self._get("/api/v1/ai/tools")

    async def get_tool(self, name: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/ai/tools/{name}")

    # --- System ---
    async def components(self) -> dict[str, Any]:
        return await self._get("/api/v1/system/components")

    async def logs(self, level: str | None = None, limit: int = 100) -> dict[str, Any]:
        return await self._get("/api/v1/system/logs", level=level, limit=limit)

    async def traces(self, limit: int = 50) -> dict[str, Any]:
        return await self._get("/api/v1/system/traces", limit=limit)
