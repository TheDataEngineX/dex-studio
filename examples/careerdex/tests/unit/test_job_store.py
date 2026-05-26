"""Tests for JobStore — DuckDB-backed CRUD for job postings."""

from __future__ import annotations

from pathlib import Path

import pytest

from careerdex.models.job import JobPosting, JobSource
from careerdex.services.job_store import JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    """Fresh store backed by a temp DuckDB file — isolated per test."""
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


class TestJobStoreInsertAndGet:
    def test_job_store_insert_and_get(self, store: JobStore, job: JobPosting) -> None:
        store.upsert(job)
        fetched = store.get(job.id)
        assert fetched is not None
        assert fetched.title == "Data Engineer"
        assert fetched.company == "Acme Corp"
        assert fetched.company_id == "acme123"
        assert fetched.remote is True
        assert fetched.salary_min == 150000
        assert fetched.salary_max == 200000
        assert fetched.required_skills == ["Python", "SQL", "DuckDB"]
        assert fetched.experience_level == "senior"
        assert fetched.source == JobSource.LINKEDIN


class TestJobStoreSearchByCompany:
    def test_job_store_search_by_company(self, store: JobStore, job: JobPosting) -> None:
        store.upsert(job)
        store.upsert(
            JobPosting(
                title="Backend Engineer",
                company="Beta Inc",
                source=JobSource.MANUAL,
            )
        )
        results = store.list_by_company("Acme Corp")
        assert len(results) == 1
        assert results[0].title == "Data Engineer"


class TestJobStoreUpsertUpdatesExisting:
    def test_job_store_upsert_updates_existing(self, store: JobStore, job: JobPosting) -> None:
        store.upsert(job)
        job.title = "Senior Data Engineer"
        job.salary_max = 250000
        store.upsert(job)
        count = store.count()
        assert count == 1
        fetched = store.get(job.id)
        assert fetched is not None
        assert fetched.title == "Senior Data Engineer"
        assert fetched.salary_max == 250000


class TestJobStoreMarkInactive:
    def test_job_store_mark_inactive(self, store: JobStore, job: JobPosting) -> None:
        store.upsert(job)
        store.mark_inactive(job.id)
        active_jobs = store.list_all(include_inactive=False)
        assert len(active_jobs) == 0
        all_jobs = store.list_all(include_inactive=True)
        assert len(all_jobs) == 1
        assert all_jobs[0].is_active is False
