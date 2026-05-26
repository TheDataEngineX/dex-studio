"""Portfolio project evaluation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import structlog

logger = structlog.get_logger(__name__)

__all__ = ["ProjectEvaluation", "evaluate_project"]


class ProjectComplexity(StrEnum):
    SIMPLE = "simple"
    MEDIUM = "complex"
    COMPLEX = "complex"


class ImpactLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ProjectEvaluation:
    """Evaluation of a portfolio project."""

    name: str
    description: str
    url: str
    complexity: ProjectComplexity
    impact: ImpactLevel
    tech_stack: list[str]
    skills_demonstrated: list[str]
    originality_score: float
    production_readiness: float
    talking_points: list[str]
    improvements: list[str]
    interview_relevance: float
    recommendation: str
    evaluated_at: datetime


def evaluate_project(
    name: str,
    description: str = "",
    url: str = "",
    tech_stack: list[str] | None = None,
) -> ProjectEvaluation:
    """Evaluate a portfolio project."""
    logger.info("project_evaluation_started", name=name)

    stack = tech_stack or ["Python", "React"]
    skills = []

    for tech in stack:
        if tech.lower() in ["python", "javascript", "typescript"]:
            skills.append(f"Software development with {tech}")
        elif tech.lower() in ["react", "vue", "angular"]:
            skills.append("Frontend development")
        elif tech.lower() in ["aws", "gcp", "azure"]:
            skills.append("Cloud infrastructure")
        elif tech.lower() in ["docker", "kubernetes"]:
            skills.append("DevOps practices")

    return ProjectEvaluation(
        name=name,
        description=description,
        url=url,
        complexity=ProjectComplexity.MEDIUM,
        impact=ImpactLevel.MEDIUM,
        tech_stack=stack,
        skills_demonstrated=skills,
        originality_score=3.5,
        production_readiness=4.0,
        talking_points=[
            "Key challenge overcome",
            "Architecture decisions",
            "Lessons learned",
        ],
        improvements=[
            "Add unit tests",
            "Improve documentation",
            "Deploy to production",
        ],
        interview_relevance=4.0,
        recommendation="Good project to discuss in interviews",
        evaluated_at=datetime.now(),
    )
