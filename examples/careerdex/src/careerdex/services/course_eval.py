"""Course/certification evaluation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import structlog

logger = structlog.get_logger(__name__)

__all__ = ["CourseEvaluation", "evaluate_course"]


class RelevanceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EffortLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class CourseEvaluation:
    """Evaluation of a course or certification."""

    name: str
    provider: str
    url: str
    relevance: RelevanceLevel
    effort: EffortLevel
    duration_hours: float | None
    cost: float | None
    skills_gained: list[str]
    certification_value: str
    roi_score: float
    recommendation: str
    alternatives: list[str]
    evaluated_at: datetime


def evaluate_course(
    name: str,
    provider: str = "",
    url: str = "",
) -> CourseEvaluation:
    """Evaluate a course or certification."""
    logger.info("course_evaluation_started", name=name)

    skills_gained = ["Skill A", "Skill B"]

    relevance = RelevanceLevel.MEDIUM
    effort = EffortLevel.MEDIUM
    roi_score = 3.5

    if "ai" in name.lower() or "ml" in name.lower():
        relevance = RelevanceLevel.HIGH
        roi_score = 4.5
        skills_gained.extend(["Machine Learning", "Deep Learning"])

    return CourseEvaluation(
        name=name,
        provider=provider,
        url=url,
        relevance=relevance,
        effort=effort,
        duration_hours=20.0,
        cost=99.0,
        skills_gained=skills_gained,
        certification_value="Industry recognized",
        roi_score=roi_score,
        recommendation="Recommended if you need these skills",
        alternatives=["Alternative course A", "Alternative course B"],
        evaluated_at=datetime.now(),
    )
