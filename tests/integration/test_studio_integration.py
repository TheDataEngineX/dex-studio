"""Integration tests — StudioStore pub/sub, DexClient HTTP, ResumeMatcher keyword mode,
and cross-service workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from careerdex.models.application import ApplicationEntry, ApplicationStatus
from careerdex.models.networking import ContactRelationship, NetworkContact
from careerdex.models.resume import ContactInfo, Resume, SkillGroup, WorkExperience
from careerdex.services.networking import NetworkingService
from careerdex.services.resume_matcher import MatchResult, ResumeMatcher
from careerdex.services.tracker import ApplicationTracker

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
# ResumeMatcher — keyword mode (no LLM)
# ---------------------------------------------------------------------------


class TestResumeMatcher:
    def test_match_text_returns_match_result(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Experienced Python developer with SQL and AWS skills",
            job_description="Looking for Python and SQL data engineer with AWS experience",
        )
        assert isinstance(result, MatchResult)
        assert 0 <= result.overall_score <= 100

    def test_match_text_finds_matched_skills(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Expert in Python, SQL, Spark, Kafka, and AWS",
            job_description="Data engineer: Python, SQL, Spark required. Kafka a plus.",
        )
        lower_matched = {s.lower() for s in result.matched_skills}
        assert "python" in lower_matched
        assert "sql" in lower_matched

    def test_match_text_identifies_missing_skills(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Python developer with no cloud experience",
            job_description="Need Python and Kubernetes and Terraform expert",
        )
        lower_missing = {s.lower() for s in result.missing_skills}
        assert "kubernetes" in lower_missing or "terraform" in lower_missing

    def test_high_overlap_high_score(self) -> None:
        matcher = ResumeMatcher()
        jd = "Python SQL Spark Kafka Airflow dbt data engineering ETL machine learning"
        resume = "Python SQL Spark Kafka Airflow dbt data engineering ETL machine learning"
        result = matcher.match_text(resume_text=resume, job_description=jd)
        assert result.overall_score >= 60

    def test_zero_overlap_low_score(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="graphic designer photoshop illustrator",
            job_description="Python SQL Spark data engineering machine learning",
        )
        assert result.overall_score < 50

    def test_match_mode_is_keyword(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text("python sql", "python developer needed")
        assert result.analysis_mode == "keyword"

    def test_match_resume_object(self) -> None:
        matcher = ResumeMatcher()
        resume = Resume(
            contact=ContactInfo(name="Jay M", title="Data Engineer"),
            summary="Python, SQL, Spark, Airflow data engineer with 5 years experience",
            skills=[
                SkillGroup(category="Data", skills=["Python", "SQL", "Spark", "Kafka", "Airflow"])
            ],
            experience=[
                WorkExperience(
                    company="Acme",
                    title="Data Engineer",
                    bullets=["Built Python ETL pipelines", "Managed SQL databases"],
                )
            ],
        )
        result = matcher.match(
            resume,
            "Python and SQL data engineer needed. Spark experience required.",
        )
        assert isinstance(result, MatchResult)
        assert result.overall_score >= 0

    def test_empty_jd_returns_50_score(self) -> None:
        # No JD keywords → no match possible; service returns neutral 50.0
        matcher = ResumeMatcher()
        result = matcher.match_text("python sql spark", "")
        assert result.overall_score == 50.0
        assert result.matched_skills == []


# ---------------------------------------------------------------------------
# Cross-service: Tracker + Networking linked by application_id
# ---------------------------------------------------------------------------


class TestTrackerNetworkingCrossService:
    def test_contact_linked_to_application(self, tmp_path: Path) -> None:
        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        net = NetworkingService(db_path=tmp_path / "net.duckdb")

        # Create application
        app = ApplicationEntry(company="DataCorp", position="Data Engineer")
        tracker.add(app)

        # Create contact linked to application
        contact = NetworkContact(
            name="Alice Recruiter",
            company="DataCorp",
            relationship=ContactRelationship.RECRUITER,
            application_id=app.id,
        )
        net.add(contact)

        # Verify linkage
        retrieved_contact = net.get(contact.id)
        assert retrieved_contact is not None
        assert retrieved_contact.application_id == app.id

        retrieved_app = tracker.get(app.id)
        assert retrieved_app is not None
        assert retrieved_app.company == "DataCorp"

        tracker.close()
        net.close()

    def test_status_progression_with_contact_interaction(self, tmp_path: Path) -> None:
        from careerdex.models.networking import Interaction, InteractionType

        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        net = NetworkingService(db_path=tmp_path / "net.duckdb")

        # Apply for job
        app = ApplicationEntry(company="TechCo", position="ML Engineer")
        tracker.add(app)
        tracker.update_status(app.id, ApplicationStatus.APPLIED)

        # Log interaction with recruiter
        contact = NetworkContact(
            name="Bob Recruiter",
            company="TechCo",
            relationship=ContactRelationship.RECRUITER,
            application_id=app.id,
        )
        net.add(contact)
        net.log_interaction(
            contact.id,
            Interaction(type=InteractionType.EMAIL, note="Reached out about ML position"),
        )

        # Move to phone screen
        tracker.update_status(app.id, ApplicationStatus.PHONE_SCREEN)

        # Verify state
        final_app = tracker.get(app.id)
        assert final_app is not None
        assert final_app.status == ApplicationStatus.PHONE_SCREEN

        final_contact = net.get(contact.id)
        assert final_contact is not None
        assert final_contact.interaction_count == 1

        tracker.close()
        net.close()

    def test_resume_match_informs_application(self, tmp_path: Path) -> None:
        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        matcher = ResumeMatcher()

        jd = "Senior Python data engineer with Spark, SQL, Kafka, and AWS experience required"
        resume_text = "Python developer with SQL databases, Spark, and AWS cloud experience"

        match_result = matcher.match_text(resume_text=resume_text, job_description=jd)

        # Use match score to decide whether to apply
        if match_result.overall_score >= 30:
            app = ApplicationEntry(
                company="DataPipelines Inc",
                position="Senior Data Engineer",
            )
            tracker.add(app)
            tracker.update_status(app.id, ApplicationStatus.APPLIED)
            tracker.add_note(app.id, f"Match score: {match_result.overall_score:.0f}%")

        entries = tracker.list_all(status=ApplicationStatus.APPLIED)
        assert len(entries) >= 1
        assert entries[0].notes[0].text.startswith("Match score:")
        tracker.close()


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
