from __future__ import annotations

import re
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import structlog

from careerdex.models.job import JobPosting, JobSource
from careerdex.services.job_search import _parse_salary

logger = structlog.get_logger()

__all__ = ["clean_description", "normalize_job"]


def clean_description(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())


def normalize_job(raw_job: dict[str, Any], source: str) -> JobPosting:
    """Transform raw API job dict to JobPosting model."""
    sal_min: float | None = None
    sal_max: float | None = None

    if salary_str := raw_job.get("salary", "") or raw_job.get("salary_range", ""):
        sal_min, sal_max = _parse_salary(salary_str)

    title = raw_job.get("title", "") or raw_job.get("job_title", "") or raw_job.get("name", "")
    company = raw_job.get("company", "") or raw_job.get("company_name", "")

    posted = None
    if date_str := (
        raw_job.get("posted_at") or raw_job.get("publication_date") or raw_job.get("created_at")
    ):
        with suppress(Exception):
            posted = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(UTC)

    source_enum: JobSource
    match source:
        case "linkedin":
            source_enum = JobSource.LINKEDIN
        case "indeed":
            source_enum = JobSource.RSS_INDEED
        case "greenhouse":
            source_enum = JobSource.GREENHOUSE
        case "lever":
            source_enum = JobSource.LEVER
        case "workday":
            source_enum = JobSource.ASHBY
        case _:
            source_enum = JobSource.MANUAL

    return JobPosting(
        title=title,
        company=company,
        location=raw_job.get("location", ""),
        remote=raw_job.get("remote", False),
        url=raw_job.get("url", "") or raw_job.get("link", ""),
        description=clean_description(raw_job.get("description", "")),
        salary_min=sal_min,
        salary_max=sal_max,
        required_skills=raw_job.get("skills", []) or raw_job.get("tags", [])[:8],
        experience_level=raw_job.get("experience_level", ""),
        employment_type=raw_job.get("employment_type", "") or "full_time",
        source=source_enum,
        posted_date=posted,
        fetched_at=datetime.now(UTC),
        is_active=True,
    )
