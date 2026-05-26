"""Job models — ported and simplified from careerdex core schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "ATSType",
    "JobSource",
    "JobPosting",
    "JobSearchQuery",
    "TrackedCompany",
    "UserProfile",
]


class ATSType(StrEnum):
    """Applicant Tracking System platform."""

    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    UNKNOWN = "unknown"


class JobSource(StrEnum):
    """Where a job posting was found."""

    RSS_INDEED = "rss_indeed"
    RSS_LINKEDIN = "rss_linkedin"
    RSS_REMOTEOK = "rss_remoteok"
    REMOTIVE_API = "remotive_api"
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    MANUAL = "manual"
    EMAIL = "email"
    REFERRAL = "referral"
    LINKEDIN = "linkedin"


class JobPosting(BaseModel):
    """A job posting — either from search or manual entry."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    title: str
    company: str
    location: str = ""
    remote: bool = False
    url: str = ""
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    required_skills: list[str] = Field(default_factory=list)
    experience_level: str = ""  # entry, mid, senior, lead, executive
    employment_type: str = "full_time"  # full_time, part_time, contract
    source: JobSource = JobSource.MANUAL
    posted_date: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    company_id: str = ""
    description_embedding: list[float] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    last_synced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobSearchQuery(BaseModel):
    """Parameters for a job search."""

    keywords: str = ""
    location: str = ""
    remote_only: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    experience_level: str = ""  # entry, mid, senior
    employment_type: str = ""  # full_time, part_time, contract, internship
    date_posted: str = ""  # all, day, week, month
    max_results: int = 25
    sources: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """Career profile for the user."""

    name: str = ""
    email: str = ""
    current_title: str = ""
    current_company: str = ""
    years_experience: int = 0
    skills: list[str] = Field(default_factory=list)
    preferred_titles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = False
    salary_expectation_min: float | None = None
    salary_expectation_max: float | None = None


class TrackedCompany(BaseModel):
    """A company whose ATS portal is scanned for live job postings."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    careers_url: str = ""
    ats_type: ATSType = ATSType.UNKNOWN
    ats_id: str = ""  # slug / board-id extracted from URL
    enabled: bool = True
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
