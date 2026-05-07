"""HTTP API client for DEX Engine."""

from __future__ import annotations

from typing import Any

import httpx

from dex_studio.config import StudioConfig

_MAX_ERROR_MSG = 500


class DexAPIError(Exception):
    """Raised when the DEX API returns an error response."""

    def __init__(self, status_code: int, message: str, url: str) -> None:
        self.status_code = status_code
        self.message = message[:_MAX_ERROR_MSG] if message else message
        self.url = url
        super().__init__(f"{status_code}: {self.message} ({url})")


class DexClient:
    """Async HTTP client for the DEX Engine API."""

    def __init__(self, config: StudioConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def config(self) -> StudioConfig:
        """Expose config for tests that access client.config."""
        return self._config

    async def connect(self) -> None:
        """Create the underlying HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._config.api_url,
            timeout=self._config.timeout,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._config.api_token:
            headers["Authorization"] = f"Bearer {self._config.api_token}"
        return headers

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, **kwargs: Any) -> dict[str, object]:
        self._assert_connected()
        assert self._client is not None
        try:
            resp = await self._client.get(path, **kwargs)
        except httpx.ConnectTimeout as exc:
            raise DexAPIError(
                status_code=0,
                message=f"Connection timeout: {exc}",
                url=self._config.api_url + path,
            ) from exc
        return self._handle_response(resp)

    async def _post(self, path: str, **kwargs: Any) -> dict[str, object]:
        self._assert_connected()
        assert self._client is not None
        try:
            resp = await self._client.post(path, **kwargs)
        except httpx.ConnectTimeout as exc:
            raise DexAPIError(
                status_code=0,
                message=f"Connection timeout: {exc}",
                url=self._config.api_url + path,
            ) from exc
        return self._handle_response(resp)

    def _assert_connected(self) -> None:
        if self._client is None:
            raise RuntimeError("not connected")

    def _handle_response(self, resp: httpx.Response) -> dict[str, object]:
        if resp.status_code >= 400:
            raise DexAPIError(
                status_code=resp.status_code,
                message=resp.text,
                url=str(resp.url),
            )
        try:
            result: dict[str, object] = resp.json()
            return result
        except ValueError as exc:
            raise DexAPIError(
                status_code=resp.status_code,
                message=f"Invalid JSON response: {exc}",
                url=str(resp.url),
            ) from exc

    # Health
    async def ping(self) -> bool:
        """Return True if the engine is reachable and healthy."""
        try:
            resp = await self._get("/api/v1/health")
            status = resp.get("status", "")
            return status in ("alive", "healthy")
        except (httpx.RequestError, DexAPIError):
            return False

    async def health(self) -> dict[str, object]:
        """Return full health status dict from /api/v1/health."""
        return await self._get("/api/v1/health")

    # Data endpoints
    async def list_sources(self) -> dict[str, object]:
        """List configured data sources."""
        return await self._get("/api/v1/data/sources")

    async def get_source(self, name: str) -> dict[str, object]:
        """Get details for a single data source."""
        return await self._get(f"/api/v1/data/sources/{name}")

    async def list_pipelines(self) -> dict[str, object]:
        """List all pipelines."""
        return await self._get("/api/v1/pipelines/")

    async def get_pipeline(self, name: str) -> dict[str, object]:
        """Get details for a single pipeline."""
        return await self._get(f"/api/v1/pipelines/{name}")

    async def run_pipeline(self, name: str) -> dict[str, object]:
        """Trigger a pipeline run."""
        return await self._post(f"/api/v1/pipelines/{name}/run")

    async def warehouse_layers(self) -> dict[str, object]:
        """List warehouse layers (bronze, silver, gold)."""
        return await self._get("/api/v1/data/warehouse/layers")

    async def warehouse_tables(self, layer: str) -> dict[str, object]:
        """List tables in a warehouse layer."""
        return await self._get(f"/api/v1/data/warehouse/{layer}/tables")

    async def list_lineage(self) -> dict[str, object]:
        """List data lineage events."""
        return await self._get("/api/v1/data/lineage")

    async def data_quality_summary(self) -> dict[str, object]:
        """Get data quality summary across pipelines."""
        return await self._get("/api/v1/data/quality")

    async def data_quality_pipeline(self, pipeline: str) -> dict[str, object]:
        """Get data quality details for a specific pipeline."""
        return await self._get(f"/api/v1/data/quality/{pipeline}")

    # ML endpoints
    async def list_experiments(self) -> dict[str, object]:
        """List ML experiments."""
        return await self._get("/api/v1/ml/experiments")

    async def create_experiment(self, name: str) -> dict[str, object]:
        """Create a new ML experiment."""
        return await self._post("/api/v1/ml/experiments", json={"name": name})

    async def list_runs(self, experiment: str) -> dict[str, object]:
        """List runs for an experiment."""
        return await self._get(f"/api/v1/ml/experiments/{experiment}/runs")

    async def get_model(self, name: str) -> dict[str, object]:
        """Get model details."""
        return await self._get(f"/api/v1/ml/models/{name}")

    async def predict(self, model_name: str, data: dict[str, object]) -> dict[str, object]:
        """Get a prediction from a model."""
        return await self._post(f"/api/v1/ml/models/{model_name}/predict", json=data)

    async def promote_model(self, name: str, stage: str) -> dict[str, object]:
        """Promote a model to a given stage (staging, production)."""
        return await self._post(f"/api/v1/ml/models/{name}/promote", json={"stage": stage})

    async def list_feature_groups(self) -> dict[str, object]:
        """List ML feature groups."""
        return await self._get("/api/v1/ml/features")

    async def get_features(
        self, group: str, entity_ids: list[str] | None = None
    ) -> dict[str, object]:
        """Get features from a feature group, optionally filtered by entity IDs."""
        params: dict[str, object] = {"group": group}
        if entity_ids:
            params["entity_ids"] = ",".join(entity_ids)
        return await self._get("/api/v1/ml/features", params=params)

    async def save_features(
        self, group: str, features: list[dict[str, object]], id_field: str
    ) -> dict[str, object]:
        """Save features to a feature group."""
        return await self._post(
            "/api/v1/ml/features",
            json={"group": group, "features": features, "id_field": id_field},
        )

    async def check_drift(self, pipeline: str) -> dict[str, object]:
        """Check data drift for a pipeline."""
        return await self._get(f"/api/v1/ml/drift/{pipeline}")

    # AI endpoints
    async def list_agents(self) -> dict[str, object]:
        """List available AI agents."""
        return await self._get("/api/v1/ai/agents")

    async def get_agent(self, name: str) -> dict[str, object]:
        """Get details for a specific agent."""
        return await self._get(f"/api/v1/ai/agents/{name}")

    async def agent_chat(self, agent: str, message: str) -> dict[str, object]:
        """Send a chat message to an agent."""
        return await self._post(f"/api/v1/ai/agents/{agent}/chat", json={"message": message})

    async def list_tools(self) -> dict[str, object]:
        """List available AI tools."""
        return await self._get("/api/v1/ai/tools")

    async def get_tool(self, name: str) -> dict[str, object]:
        """Get details for a specific tool."""
        return await self._get(f"/api/v1/ai/tools/{name}")

    # System endpoints
    async def components(self) -> dict[str, object]:
        """List system components."""
        return await self._get("/api/v1/system/components")

    async def logs(self, level: str | None = None, limit: int = 100) -> dict[str, object]:
        """Fetch system logs with optional level filter."""
        params: dict[str, object] = {"limit": limit}
        if level:
            params["level"] = level
        return await self._get("/api/v1/system/logs", params=params)

    async def traces(self, limit: int = 100) -> dict[str, object]:
        """Fetch system traces."""
        return await self._get("/api/v1/system/traces", params={"limit": limit})
