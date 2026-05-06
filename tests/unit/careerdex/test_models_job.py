"""Unit tests for careerdex job models."""

from __future__ import annotations

from datetime import UTC, datetime

from careerdex.models.job import (
    JobPosting,
    JobSearchQuery,
    JobSource,
    UserProfile,
)


class TestJobSource:
    def test_all_enum_values_exist(self) -> None:
        assert JobSource.RSS_INDEED == "rss_indeed"
        assert JobSource.RSS_LINKEDIN == "rss_linkedin"
        assert JobSource.RSS_REMOTEOK == "rss_remoteok"
        assert JobSource.REMOTIVE_API == "remotive_api"
        assert JobSource.GREENHOUSE == "greenhouse"
        assert JobSource.ASHBY == "ashby"
        assert JobSource.LEVER == "lever"
        assert JobSource.MANUAL == "manual"
        assert JobSource.EMAIL == "email"
        assert JobSource.REFERRAL == "referral"

    def test_is_str_enum(self) -> None:
        assert str(JobSource.MANUAL) == "manual"

    def test_count(self) -> None:
        assert len(JobSource) == 11


class TestJobPostingDefaults:
    def test_id_generated(self) -> None:
        j1 = JobPosting(title="A", company="B")
        j2 = JobPosting(title="A", company="B")
        assert j1.id != j2.id
        assert len(j1.id) == 16

    def test_fetched_at_set(self) -> None:
        before = datetime.now(UTC)
        j = JobPosting(title="A", company="B")
        after = datetime.now(UTC)
        assert before <= j.fetched_at <= after

    def test_salary_none_by_default(self) -> None:
        j = JobPosting(title="A", company="B")
        assert j.salary_min is None
        assert j.salary_max is None

    def test_source_default_manual(self) -> None:
        j = JobPosting(title="A", company="B")
        assert j.source == JobSource.MANUAL

    def test_remote_default_false(self) -> None:
        j = JobPosting(title="A", company="B")
        assert j.remote is False

    def test_required_skills_empty_list(self) -> None:
        j = JobPosting(title="A", company="B")
        assert j.required_skills == []

    def test_posted_date_none(self) -> None:
        j = JobPosting(title="A", company="B")
        assert j.posted_date is None


class TestJobPostingAllFields:
    def test_full_posting(self) -> None:
        now = datetime.now(UTC)
        j = JobPosting(
            title="Data Engineer",
            company="Acme",
            location="New York",
            remote=True,
            url="https://example.com/job/1",
            description="Build pipelines",
            salary_min=120_000.0,
            salary_max=150_000.0,
            salary_currency="USD",
            required_skills=["Python", "Spark"],
            experience_level="senior",
            employment_type="full_time",
            source=JobSource.REMOTIVE_API,
            posted_date=now,
        )
        assert j.title == "Data Engineer"
        assert j.company == "Acme"
        assert j.salary_min == 120_000.0
        assert j.salary_max == 150_000.0
        assert j.required_skills == ["Python", "Spark"]
        assert j.source == JobSource.REMOTIVE_API
        assert j.posted_date == now
        assert j.remote is True


class TestJobSearchQuery:
    def test_defaults(self) -> None:
        q = JobSearchQuery()
        assert q.keywords == ""
        assert q.location == ""
        assert q.remote_only is False
        assert q.salary_min is None
        assert q.experience_level == ""
        assert q.max_results == 25

    def test_custom_values(self) -> None:
        q = JobSearchQuery(
            keywords="data engineer",
            location="remote",
            remote_only=True,
            salary_min=100_000.0,
            experience_level="senior",
            max_results=10,
        )
        assert q.keywords == "data engineer"
        assert q.remote_only is True
        assert q.salary_min == 100_000.0
        assert q.max_results == 10


class TestUserProfile:
    def test_defaults(self) -> None:
        p = UserProfile()
        assert p.name == ""
        assert p.email == ""
        assert p.current_title == ""
        assert p.current_company == ""
        assert p.years_experience == 0
        assert p.skills == []
        assert p.preferred_titles == []
        assert p.preferred_locations == []
        assert p.willing_to_relocate is False
        assert p.salary_expectation_min is None
        assert p.salary_expectation_max is None

    def test_skills_list(self) -> None:
        p = UserProfile(skills=["Python", "SQL", "Spark"])
        assert len(p.skills) == 3
        assert "SQL" in p.skills

    def test_preferred_locations_independent(self) -> None:
        p1 = UserProfile()
        p2 = UserProfile()
        p1.preferred_locations.append("NYC")
        assert p2.preferred_locations == []
