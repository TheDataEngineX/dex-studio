from __future__ import annotations

import re
from abc import ABC, abstractmethod

import structlog

from careerdex.models.job import JobPosting

logger = structlog.get_logger()

__all__ = ["BaseJobSource", "SourceRegistry", "normalize_company"]


def normalize_company(name: str) -> str:
    """Slugify company name: lowercase, remove non-alphanumeric, limit 40 chars."""
    if not name:
        return ""
    slug = re.sub(r"[^a-z0-9]", "", name.lower())
    return slug[:40]


class BaseJobSource(ABC):
    """Abstract base class for job sources."""

    name: str = "base"
    base_url: str = ""

    @abstractmethod
    async def fetch(self) -> list[JobPosting]:
        """Fetch all jobs from this source."""
        ...

    @abstractmethod
    async def fetch_company_jobs(self, company_slug: str) -> list[JobPosting]:
        """Fetch jobs for a specific company."""
        ...


class SourceRegistry:
    """Registry for job source classes."""

    _sources: dict[str, type[BaseJobSource]] = {}

    @classmethod
    def register(cls, name: str, source_cls: type[BaseJobSource]) -> None:
        """Register a source class."""
        cls._sources[name] = source_cls

    @classmethod
    def get(cls, name: str) -> type[BaseJobSource] | None:
        """Get a source class by name."""
        return cls._sources.get(name)

    @classmethod
    def list_sources(cls) -> list[str]:
        """List all registered source names."""
        return list(cls._sources.keys())

    @classmethod
    def autodiscover(cls) -> None:
        """Auto-register all JobSource subclasses."""
        from careerdex.services.aggregator import (
            GreenhouseSource,
            IndeedSource,
            LeverSource,
            LinkedInSource,
            WorkdaySource,
        )

        for source_cls in (
            LinkedInSource,
            IndeedSource,
            GreenhouseSource,
            LeverSource,
            WorkdaySource,
        ):
            cls.register(source_cls.name, source_cls)  # type: ignore[arg-type]
            logger.info("autodiscovered_source", name=source_cls.name)
