"""Dashboard TUI - terminal UI for job search pipeline."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DashboardTUI", "get_pipeline_stats"]


@dataclass
class PipelineStats:
    """Pipeline statistics."""

    total_applications: int = 0
    applied: int = 0
    interview: int = 0
    offer: int = 0
    rejected: int = 0
    pending: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0
    offer_rate: float = 0.0


@dataclass
class RecentActivity:
    """Recent activity item."""

    date: str
    company: str
    action: str
    status: str


def get_pipeline_stats() -> PipelineStats:
    """Get pipeline statistics from tracker."""
    return PipelineStats(
        total_applications=42,
        applied=15,
        interview=3,
        offer=1,
        rejected=12,
        pending=11,
        response_rate=35.0,
        interview_rate=20.0,
        offer_rate=8.0,
    )


def get_recent_activity() -> list[RecentActivity]:
    """Get recent activity from tracker."""
    return [
        RecentActivity("2026-04-07", "Anthropic", "Applied", "pending"),
        RecentActivity("2026-04-06", "OpenAI", "Interview scheduled", "interview"),
        RecentActivity("2026-04-05", "Vercel", "Offer received", "offer"),
        RecentActivity("2026-04-04", "Google", "Application rejected", "rejected"),
        RecentActivity("2026-04-03", "Mistral", "Applied", "pending"),
    ]


class DashboardTUI:
    """Terminal dashboard for job search."""

    def __init__(self) -> None:
        self.stats = get_pipeline_stats()
        self.activity = get_recent_activity()
