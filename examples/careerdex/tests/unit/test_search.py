"""Tests for JobService — combined local store + live aggregation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from careerdex.models.job import JobPosting, JobSearchQuery, JobSource
from careerdex.services.job_store import JobStore
from careerdex.services.search import JobService


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    """Fresh store backed by a temp DuckDB file."""
    s = JobStore(db_path=tmp_path / "test.duckdb")
    yield s
    s.close()


@pytest.fixture
def job() -> JobPosting:
    return JobPosting(
        title="Data Engineer",
        company="Acme Corp",
        company_id="acme123",
        location="San Francisco, CA",
        remote=True,
        url="https://acme.com/jobs/123",
        description="Build data pipelines",
        salary_min=150000,
        salary_max=200000,
        required_skills=["Python", "SQL", "DuckDB"],
        experience_level="senior",
        employment_type="full_time",
        source=JobSource.LINKEDIN,
    )


class TestJobServiceSearchEmpty:
    def test_job_service_search_empty(self, store: JobStore) -> None:
        svc = JobService(store=store)
        results = svc.search(JobSearchQuery(keywords="data engineer"))
        svc.close()
        assert results == []


class TestJobServiceSearchWithResults:
    def test_job_service_search_with_results(self, store: JobStore, job: JobPosting) -> None:
        store.upsert(job)
        svc = JobService(store=store)
        results = svc.search(JobSearchQuery(keywords="data"))
        svc.close()
        assert len(results) == 1
        assert results[0].title == "Data Engineer"


class TestJobServiceRefreshSource:
    @pytest.mark.asyncio
    async def test_job_service_refresh_source(self, store: JobStore, job: JobPosting) -> None:
        from careerdex.services.aggregator import SourceRegistry

        mock_source_cls = MagicMock()
        mock_source_instance = AsyncMock()
        mock_source_instance.fetch = AsyncMock(return_value=[job])
        mock_source_cls.return_value = mock_source_instance
        mock_source_cls.name = "test_source"
        mock_source_cls.base_url = "http://test.com"

        SourceRegistry.register("test_source", mock_source_cls)

        svc = JobService(store=store)
        count = await svc.refresh_source("test_source", limit=10)

        assert count == 1
        fetched = store.get(job.id)
        assert fetched is not None
        assert fetched.title == "Data Engineer"

        svc.close()
