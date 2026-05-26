"""Portal scanner data models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ATSPlatform(StrEnum):
    ASHBY = "ashby"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    CUSTOM = "custom"


class ScanStatus(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"
    FILTERED = "filtered"
    ADDED = "added"


class TitleFilter(BaseModel):
    positive: list[str] = Field(
        default_factory=lambda: [
            "engineer",
            "developer",
            "ml",
            "ai",
            "data",
            "scientist",
            "architect",
        ]
    )
    negative: list[str] = Field(
        default_factory=lambda: ["intern", "contractor", "sales", "marketing"]
    )
    seniority_boost: list[str] = Field(
        default_factory=lambda: ["senior", "staff", "principal", "lead", "manager"]
    )


class PortalCompany(BaseModel):
    name: str
    slug: str
    careers_url: str | None = None
    ats_platform: ATSPlatform = ATSPlatform.CUSTOM
    enabled: bool = True
    industry: str = "tech"


class ScanResult(BaseModel):
    url: str
    title: str
    company: str
    source: str = "playwright"
    status: ScanStatus = ScanStatus.NEW
    discovered_at: datetime = Field(default_factory=datetime.now)


class ScanSummary(BaseModel):
    companies_scanned: int
    jobs_found: int
    jobs_filtered: int
    jobs_duplicates: int
    jobs_added: int
    scan_duration_seconds: float
    errors: list[str] = Field(default_factory=list)
