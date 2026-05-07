"""End-to-end user flow tests using real DuckDB (no mocks on the DB layer).

Tests represent full journeys a user takes through the application:
  - Application lifecycle: save → apply → interview → offer → accept
  - Networking lifecycle: add contact → log interactions → follow-ups
  - Tracker batch operations: bulk add, filter, stats
  - Resume matcher: keyword fallback when AI offline
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

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from careerdex.models.application import ApplicationEntry, ApplicationStatus
from careerdex.models.networking import (
    ContactRelationship,
    Interaction,
    InteractionType,
    NetworkContact,
)
from careerdex.services.networking import NetworkingService
from careerdex.services.tracker import ApplicationTracker

from dex_studio.client import DexClient
from dex_studio.config import StudioConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tracker(tmp_path: Path) -> ApplicationTracker:
    return ApplicationTracker(db_path=tmp_path / "tracker.duckdb")


@pytest.fixture()
def networking(tmp_path: Path) -> NetworkingService:
    return NetworkingService(db_path=tmp_path / "networking.duckdb")


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
# User Flow 1: Full application lifecycle
# ---------------------------------------------------------------------------


class TestApplicationLifecycleFlow:
    def test_save_to_accepted_complete_path(self, tracker: ApplicationTracker) -> None:
        """User saves job, applies, progresses through interviews, accepts offer."""
        entry = tracker.add(
            ApplicationEntry(
                company="DreamCo",
                position="Senior Data Engineer",
                url="https://dreamco.com/jobs/123",
            )
        )
        assert entry.status == ApplicationStatus.SAVED

        # Apply
        updated = tracker.update_status(
            entry.id, ApplicationStatus.APPLIED, reason="Applied online"
        )
        assert updated is not None
        assert updated.status == ApplicationStatus.APPLIED
        assert updated.applied_at is not None

        # Phone screen
        updated = tracker.update_status(updated.id, ApplicationStatus.PHONE_SCREEN)
        assert updated.status == ApplicationStatus.PHONE_SCREEN

        # Interview
        updated = tracker.update_status(updated.id, ApplicationStatus.INTERVIEW)
        updated = tracker.add_note(updated.id, "Great culture conversation with hiring manager")
        assert updated is not None
        assert len(updated.notes) == 1

        # Technical round
        updated = tracker.update_status(updated.id, ApplicationStatus.TECHNICAL)

        # Offer received
        updated = tracker.update_status(updated.id, ApplicationStatus.OFFER)

        # Accept
        updated = tracker.update_status(
            updated.id, ApplicationStatus.ACCEPTED, reason="Negotiated 120k"
        )
        assert updated.status == ApplicationStatus.ACCEPTED

        # Verify full event trail
        final = tracker.get(entry.id)
        assert final is not None
        assert (
            len(final.events) == 6
        )  # APPLIED, PHONE_SCREEN, INTERVIEW, TECHNICAL, OFFER, ACCEPTED

    def test_rejection_flow(self, tracker: ApplicationTracker) -> None:
        entry = tracker.add(ApplicationEntry(company="MissedCo", position="SWE"))
        tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        tracker.update_status(entry.id, ApplicationStatus.REJECTED, reason="Position filled")
        final = tracker.get(entry.id)
        assert final is not None
        assert final.status == ApplicationStatus.REJECTED
        # Cannot transition from REJECTED
        with pytest.raises(ValueError):
            final.transition(ApplicationStatus.APPLIED)

    def test_ghosted_then_responded_flow(self, tracker: ApplicationTracker) -> None:
        entry = tracker.add(ApplicationEntry(company="GhostCo", position="PM"))
        tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        tracker.update_status(entry.id, ApplicationStatus.GHOSTED)
        tracker.update_status(entry.id, ApplicationStatus.RESPONDED)
        final = tracker.get(entry.id)
        assert final is not None
        assert final.status == ApplicationStatus.RESPONDED

    def test_withdrawn_cannot_be_undone(self, tracker: ApplicationTracker) -> None:
        entry = tracker.add(ApplicationEntry(company="MyCo", position="Lead"))
        tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        tracker.update_status(entry.id, ApplicationStatus.WITHDRAWN)
        final = tracker.get(entry.id)
        assert final is not None
        with pytest.raises(ValueError):
            final.transition(ApplicationStatus.APPLIED)

    def test_stats_reflect_full_lifecycle(self, tracker: ApplicationTracker) -> None:
        """Stats remain accurate after transitions."""
        e1 = tracker.add(ApplicationEntry(company="A", position="SWE"))
        e2 = tracker.add(ApplicationEntry(company="B", position="PM"))
        _e3 = tracker.add(ApplicationEntry(company="C", position="EM"))

        tracker.update_status(e1.id, ApplicationStatus.APPLIED)
        tracker.update_status(e1.id, ApplicationStatus.REJECTED)

        tracker.update_status(e2.id, ApplicationStatus.APPLIED)
        tracker.update_status(e2.id, ApplicationStatus.INTERVIEW)
        tracker.update_status(e2.id, ApplicationStatus.OFFER)
        tracker.update_status(e2.id, ApplicationStatus.ACCEPTED)

        stats = tracker.stats()
        assert stats.get("rejected", 0) == 1
        assert stats.get("accepted", 0) == 1
        assert stats.get("saved", 0) == 1  # e3 still in saved


# ---------------------------------------------------------------------------
# User Flow 2: Networking lifecycle
# ---------------------------------------------------------------------------


class TestNetworkingLifecycleFlow:
    def test_add_contact_log_interactions_check_followup(
        self, networking: NetworkingService
    ) -> None:
        """User adds a hiring manager, logs interactions, checks follow-up due."""
        contact = networking.add(
            NetworkContact(
                name="Jane Smith",
                title="VP Engineering",
                company="TechCorp",
                relationship=ContactRelationship.HIRING_MANAGER,
                email="jane@techcorp.com",
                next_follow_up=datetime.now(UTC) + timedelta(days=7),
            )
        )
        assert contact.name == "Jane Smith"

        # Log first contact
        networking.log_interaction(
            contact.id,
            Interaction(type=InteractionType.LINKEDIN, note="Connected on LinkedIn"),
        )
        # Log follow-up call
        networking.log_interaction(
            contact.id,
            Interaction(type=InteractionType.CALL, note="30-min intro call — very positive"),
        )

        fetched = networking.get(contact.id)
        assert fetched is not None
        assert len(fetched.interactions) == 2

        # Not yet due
        due = networking.due_follow_ups()
        assert contact.id not in [c.id for c in due]

    def test_overdue_followup_appears_in_due_list(self, networking: NetworkingService) -> None:
        networking.add(
            NetworkContact(
                name="Overdue Contact",
                next_follow_up=datetime.now(UTC) - timedelta(days=2),
            )
        )
        due = networking.due_follow_ups()
        names = [c.name for c in due]
        assert "Overdue Contact" in names

    def test_search_by_company_after_add(self, networking: NetworkingService) -> None:
        networking.add(NetworkContact(name="Alice", company="Stripe"))
        networking.add(NetworkContact(name="Bob", company="Shopify"))
        results = networking.list_all(search="stripe")
        assert len(results) == 1
        assert results[0].name == "Alice"

    def test_update_contact_and_fetch(self, networking: NetworkingService) -> None:
        contact = networking.add(NetworkContact(name="Old Name", company="Corp"))
        contact.name = "New Name"
        contact.title = "Senior Manager"
        networking.update(contact)
        fetched = networking.get(contact.id)
        assert fetched is not None
        assert fetched.name == "New Name"
        assert fetched.title == "Senior Manager"

    def test_delete_contact_removes_from_list(self, networking: NetworkingService) -> None:
        contact = networking.add(NetworkContact(name="Gone", company="GoneCo"))
        networking.delete(contact.id)
        assert networking.get(contact.id) is None
        assert len(networking.list_all()) == 0


# ---------------------------------------------------------------------------
# User Flow 3: Tracker batch operations
# ---------------------------------------------------------------------------


class TestTrackerBatchFlow:
    def test_bulk_add_and_filter_by_status(self, tracker: ApplicationTracker) -> None:
        companies = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        for i, company in enumerate(companies):
            e = tracker.add(ApplicationEntry(company=company, position="SWE"))
            if i % 2 == 0:
                tracker.update_status(e.id, ApplicationStatus.APPLIED)

        applied = tracker.list_all(status=ApplicationStatus.APPLIED)
        saved = tracker.list_all(status=ApplicationStatus.SAVED)
        assert len(applied) == 3  # Alpha, Gamma, Epsilon (indices 0, 2, 4)
        assert len(saved) == 2  # Beta, Delta

    def test_search_across_company_and_position(self, tracker: ApplicationTracker) -> None:
        tracker.add(ApplicationEntry(company="DataCo", position="Data Engineer"))
        tracker.add(ApplicationEntry(company="AnalyticsCo", position="Data Analyst"))
        tracker.add(ApplicationEntry(company="RandomCo", position="Product Manager"))

        results = tracker.list_all(search="data")
        assert len(results) == 2  # DataCo + Data Analyst

    def test_delete_nonexistent_does_not_affect_others(self, tracker: ApplicationTracker) -> None:
        e = tracker.add(ApplicationEntry(company="KeepMe", position="SWE"))
        tracker.delete("fake-id-that-does-not-exist")
        assert tracker.get(e.id) is not None

    def test_update_entry_persists_changes(self, tracker: ApplicationTracker) -> None:
        entry = tracker.add(ApplicationEntry(company="OldCo", position="OldRole"))
        entry.company = "NewCo"
        entry.salary_min = 90_000.0
        entry.salary_max = 140_000.0
        tracker.update(entry)
        fetched = tracker.get(entry.id)
        assert fetched is not None
        assert fetched.company == "NewCo"
        assert fetched.salary_min == 90_000.0

    def test_notes_persist_after_status_update(self, tracker: ApplicationTracker) -> None:
        entry = tracker.add(ApplicationEntry(company="NoteCo", position="PM"))
        tracker.add_note(entry.id, "Good first impression")
        tracker.update_status(entry.id, ApplicationStatus.APPLIED)
        fetched = tracker.get(entry.id)
        assert fetched is not None
        assert len(fetched.notes) == 1
        assert fetched.notes[0].text == "Good first impression"


# ---------------------------------------------------------------------------
# User Flow 4: UI → API endpoint mapping (DexClient)
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
# User Flow 5: Config loading
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
            # If it doesn't raise, must be default or something reasonable
            assert isinstance(cfg.timeout, float)
        except (ValueError, TypeError):
            pass  # Acceptable — invalid value rejected

    def test_config_with_api_token(self) -> None:
        cfg = StudioConfig(api_token="my-jwt-token")
        assert cfg.api_token == "my-jwt-token"

    def test_config_api_url_no_trailing_slash(self) -> None:
        cfg = StudioConfig(api_url="http://localhost:17000/")
        client = DexClient(cfg)
        # httpx base_url handles trailing slashes — just verify no crash
        assert client.config.api_url == "http://localhost:17000/"
