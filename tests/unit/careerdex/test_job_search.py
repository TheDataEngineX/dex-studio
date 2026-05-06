"""Unit tests for JobSearchService and utility functions."""

from __future__ import annotations

import unittest.mock
from datetime import UTC, datetime

from careerdex.models.job import JobPosting, JobSearchQuery, JobSource
from careerdex.services.job_search import (
    JobSearchService,
    _apply_filters,
    _normalize_to_utc,
    _parse_rss_date,
    _parse_salary,
    _strip_html,
)


class TestParseSalary:
    def test_k_notation(self) -> None:
        lo, hi = _parse_salary("$120k - $150k")
        assert lo == 120_000.0
        assert hi == 150_000.0

    def test_comma_notation(self) -> None:
        lo, hi = _parse_salary("$80,000 - $100,000")
        assert lo == 80_000.0
        assert hi == 100_000.0

    def test_no_salary(self) -> None:
        lo, hi = _parse_salary("competitive compensation")
        assert lo is None
        assert hi is None

    def test_empty_string(self) -> None:
        lo, hi = _parse_salary("")
        assert lo is None
        assert hi is None

    def test_euro_symbol(self) -> None:
        lo, hi = _parse_salary("€60k - €80k")
        assert lo == 60_000.0
        assert hi == 80_000.0


class TestStripHtml:
    def test_removes_tags(self) -> None:
        result = _strip_html("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_plain_text_unchanged(self) -> None:
        result = _strip_html("plain text")
        assert result == "plain text"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""

    def test_strips_surrounding_whitespace(self) -> None:
        result = _strip_html("  <p>hi</p>  ")
        assert result == result.strip()


class TestParseRssDate:
    def test_none_returns_none(self) -> None:
        assert _parse_rss_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_rss_date("") is None

    def test_rfc2822_date(self) -> None:
        result = _parse_rss_date("Tue, 01 Jan 2026 00:00:00 +0000")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1

    def test_iso8601_date(self) -> None:
        result = _parse_rss_date("2026-01-15T12:00:00Z")
        assert isinstance(result, datetime)
        assert result.year == 2026

    def test_invalid_returns_none(self) -> None:
        assert _parse_rss_date("not a date") is None


class TestNormalizeToUtc:
    def test_naive_datetime_gets_utc(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = _normalize_to_utc(naive)
        assert result.tzinfo is not None

    def test_aware_datetime_converted(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = _normalize_to_utc(aware)
        assert result.tzinfo is not None


class TestApplyFilters:
    def _make_job(self, **kwargs: object) -> JobPosting:
        defaults: dict[str, object] = {
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Remote",
            "remote": True,
        }
        defaults.update(kwargs)
        return JobPosting(**defaults)  # type: ignore[arg-type]

    def test_location_filter(self) -> None:
        jobs = [
            self._make_job(location="New York"),
            self._make_job(location="London"),
        ]
        query = JobSearchQuery(location="new york")
        result = _apply_filters(jobs, query)
        assert len(result) == 1
        assert result[0].location == "New York"

    def test_remote_only_filter(self) -> None:
        jobs = [
            self._make_job(remote=True),
            self._make_job(remote=False),
        ]
        query = JobSearchQuery(remote_only=True)
        result = _apply_filters(jobs, query)
        assert all(j.remote for j in result)

    def test_salary_min_filter(self) -> None:
        jobs = [
            self._make_job(salary_max=50_000),
            self._make_job(salary_max=150_000),
        ]
        query = JobSearchQuery(salary_min=100_000.0)
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_no_filters_returns_all(self) -> None:
        jobs = [self._make_job(), self._make_job(company="Beta")]
        query = JobSearchQuery()
        result = _apply_filters(jobs, query)
        assert len(result) == 2


class TestJobSearchServiceRemotive:
    def _remotive_response(self) -> dict[str, object]:
        return {
            "jobs": [
                {
                    "id": 1,
                    "title": "Data Engineer",
                    "company_name": "TechCorp",
                    "candidate_required_location": "Worldwide",
                    "url": "https://example.com/job/1",
                    "description": "<p>Build pipelines</p>",
                    "salary": "$120k - $150k",
                    "tags": ["python", "spark"],
                    "job_type": "full_time",
                    "publication_date": "2026-01-01T00:00:00",
                }
            ]
        }

    def test_search_remotive_returns_postings(self) -> None:
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = self._remotive_response()
        mock_resp.raise_for_status.return_value = None

        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", return_value=mock_resp):
                jobs = svc._search_remotive(JobSearchQuery(keywords="data engineer"))

        assert len(jobs) == 1
        assert jobs[0].title == "Data Engineer"
        assert jobs[0].company == "TechCorp"
        assert jobs[0].remote is True
        assert jobs[0].source == JobSource.REMOTIVE_API

    def test_search_remotive_parses_salary(self) -> None:
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = self._remotive_response()
        mock_resp.raise_for_status.return_value = None

        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", return_value=mock_resp):
                jobs = svc._search_remotive(JobSearchQuery())

        assert jobs[0].salary_min == 120_000.0
        assert jobs[0].salary_max == 150_000.0

    def test_search_remotive_returns_empty_on_error(self) -> None:
        import httpx

        err = httpx.ConnectError("down")
        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", side_effect=err):
                jobs = svc._search_remotive(JobSearchQuery())

        assert jobs == []

    def test_search_deduplicates_by_url(self) -> None:
        """search() calls _search_remotive twice — deduplicate should collapse them."""
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = self._remotive_response()
        mock_resp.raise_for_status.return_value = None

        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", return_value=mock_resp):
                results = svc.search(JobSearchQuery(keywords="data engineer"))

        urls = [j.url for j in results]
        assert len(urls) == len(set(urls))

    def test_context_manager(self) -> None:
        with JobSearchService() as svc:  # noqa: SIM117
            assert svc._client is not None


class TestApplyFiltersExtended:
    def _make_job(self, **kwargs: object) -> JobPosting:
        defaults: dict[str, object] = {
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Remote",
            "remote": True,
        }
        defaults.update(kwargs)
        return JobPosting(**defaults)  # type: ignore[arg-type]

    def test_salary_max_filter(self) -> None:
        jobs = [
            self._make_job(salary_min=200_000),
            self._make_job(salary_min=50_000),
        ]
        query = JobSearchQuery(salary_max=100_000.0)
        result = _apply_filters(jobs, query)
        assert len(result) == 1
        assert result[0].salary_min == 50_000

    def test_experience_level_filter(self) -> None:
        jobs = [
            self._make_job(experience_level="senior"),
            self._make_job(experience_level="entry"),
        ]
        query = JobSearchQuery(experience_level="senior")
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_employment_type_filter(self) -> None:
        jobs = [
            self._make_job(employment_type="full_time"),
            self._make_job(employment_type="contract"),
        ]
        query = JobSearchQuery(employment_type="contract")
        result = _apply_filters(jobs, query)
        assert len(result) == 1
        assert result[0].employment_type == "contract"

    def test_date_posted_day_filter(self) -> None:
        from datetime import UTC, timedelta
        from datetime import datetime as dt

        recent = dt.now(UTC) - timedelta(hours=1)
        old = dt.now(UTC) - timedelta(days=10)
        jobs = [
            self._make_job(posted_date=recent),
            self._make_job(posted_date=old),
        ]
        query = JobSearchQuery(date_posted="day")
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_date_posted_week_filter(self) -> None:
        from datetime import UTC, timedelta
        from datetime import datetime as dt

        recent = dt.now(UTC) - timedelta(days=3)
        old = dt.now(UTC) - timedelta(days=30)
        jobs = [
            self._make_job(posted_date=recent),
            self._make_job(posted_date=old),
        ]
        query = JobSearchQuery(date_posted="week")
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_date_posted_month_filter(self) -> None:
        from datetime import UTC, timedelta
        from datetime import datetime as dt

        recent = dt.now(UTC) - timedelta(days=15)
        old = dt.now(UTC) - timedelta(days=60)
        jobs = [
            self._make_job(posted_date=recent),
            self._make_job(posted_date=old),
        ]
        query = JobSearchQuery(date_posted="month")
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_date_posted_none_passes_through(self) -> None:
        jobs = [self._make_job(posted_date=None)]
        query = JobSearchQuery(date_posted="day")
        result = _apply_filters(jobs, query)
        assert len(result) == 1  # None posted_date is always included

    def test_date_posted_all_no_filter(self) -> None:
        from datetime import UTC, timedelta
        from datetime import datetime as dt

        old = dt.now(UTC) - timedelta(days=100)
        jobs = [self._make_job(posted_date=old)]
        query = JobSearchQuery(date_posted="all")
        result = _apply_filters(jobs, query)
        assert len(result) == 1


class TestJobSearchServiceJooble:
    def test_search_jooble_called_with_api_key(self) -> None:
        import careerdex.services.job_search as js_module

        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "company": "Corp",
                    "location": "Remote",
                    "link": "https://jooble.org/1",
                    "snippet": "<p>Backend work</p>",
                    "salary": "",
                    "publicationDate": "2026-01-01T00:00:00",
                }
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch.object(js_module, "_JOBBLE_API_KEY", "test-key"):  # noqa: SIM117
            with JobSearchService() as svc:  # noqa: SIM117
                with unittest.mock.patch.object(svc._client, "post", return_value=mock_resp):
                    jobs = svc._search_jooble(JobSearchQuery(keywords="backend"))

        assert len(jobs) == 1
        assert jobs[0].title == "Backend Engineer"

    def test_search_jooble_remote_flag(self) -> None:
        import careerdex.services.job_search as js_module

        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"jobs": []}
        mock_resp.raise_for_status.return_value = None

        patch_key = unittest.mock.patch.object(js_module, "_JOBBLE_API_KEY", "test-key")
        with patch_key:  # noqa: SIM117
            with JobSearchService() as svc:  # noqa: SIM117
                patcher = unittest.mock.patch.object(svc._client, "post", return_value=mock_resp)
                with patcher as mock_post:
                    svc._search_jooble(JobSearchQuery(remote_only=True))
                    call_kwargs = mock_post.call_args
                    assert call_kwargs[1]["json"]["remote"] is True

    def test_search_jooble_returns_empty_on_error(self) -> None:
        import careerdex.services.job_search as js_module
        import httpx

        err = httpx.ConnectError("down")
        with unittest.mock.patch.object(js_module, "_JOBBLE_API_KEY", "test-key"):  # noqa: SIM117
            with JobSearchService() as svc:  # noqa: SIM117
                with unittest.mock.patch.object(svc._client, "post", side_effect=err):
                    jobs = svc._search_jooble(JobSearchQuery())

        assert jobs == []


class TestJobSearchServiceArbeitnow:
    def test_search_arbeitnow_returns_postings(self) -> None:
        api_resp = {
            "data": [
                {
                    "slug": "de-acme-123",
                    "title": "ML Engineer",
                    "company_name": "Acme",
                    "location": "Berlin",
                    "remote": True,
                    "description": "<p>ML work</p>",
                    "tags": ["python", "ml"],
                    "job_types": ["full_time"],
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = api_resp
        mock_resp.raise_for_status.return_value = None

        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", return_value=mock_resp):
                jobs = svc._search_arbeitnow(JobSearchQuery(keywords="ml"))

        assert len(jobs) == 1
        assert jobs[0].title == "ML Engineer"

    def test_search_arbeitnow_returns_empty_on_error(self) -> None:
        import httpx

        err = httpx.ConnectError("down")
        with JobSearchService() as svc:  # noqa: SIM117
            with unittest.mock.patch.object(svc._client, "get", side_effect=err):
                jobs = svc._search_arbeitnow(JobSearchQuery())

        assert jobs == []


class TestJobSearchEdgeCases:
    def _make_job(self, **kwargs: object) -> JobPosting:
        defaults: dict[str, object] = {
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Remote",
            "remote": True,
        }
        defaults.update(kwargs)
        return JobPosting(**defaults)

    def test_parse_salary_with_symbols(self) -> None:
        lo, hi = _parse_salary("$120k - $150k")
        assert lo == 120_000.0
        assert hi == 150_000.0

    def test_parse_salary_invalid(self) -> None:
        assert _parse_salary("N/A") == (None, None)
        assert _parse_salary("Negotiable") == (None, None)
        assert _parse_salary("DOE") == (None, None)

    def test_parse_salary_euro(self) -> None:
        lo, hi = _parse_salary("€60k - €80k")
        assert lo == 60_000.0
        assert hi == 80_000.0

    def test_strip_html_weird_chars(self) -> None:
        result = _strip_html("<script>alert('xss')</script><p>text</p>")
        assert "<script>" not in result
        assert "text" in result

    def test_strip_html_malformed(self) -> None:
        result = _strip_html("<p>unclosed")
        assert "unclosed" in result

    def test_apply_filters_salary_range(self) -> None:
        jobs = [
            self._make_job(salary_min=50_000, salary_max=60_000),
            self._make_job(salary_min=80_000, salary_max=120_000),
        ]
        query = JobSearchQuery(salary_min=70_000.0)
        result = _apply_filters(jobs, query)
        assert len(result) == 1

    def test_apply_filters_empty_results(self) -> None:
        query = JobSearchQuery(location="nonexistent")
        result = _apply_filters([], query)
        assert result == []

    def test_apply_filters_location_case_insensitive(self) -> None:
        jobs = [
            self._make_job(location="New York"),
            self._make_job(location="new york"),
        ]
        query = JobSearchQuery(location="NEW YORK")
        result = _apply_filters(jobs, query)
        assert len(result) == 2

    def test_apply_filters_all_jobs_preserved(self) -> None:
        jobs = [
            self._make_job(title="Data Engineer"),
            self._make_job(title="Designer"),
        ]
        query = JobSearchQuery()
        result = _apply_filters(jobs, query)
        assert len(result) == 2
