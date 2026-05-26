"""Progress tracking models — periodic skill snapshots and delta computation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "SkillCategory",
    "SkillRating",
    "SkillSnapshot",
    "SkillDelta",
]


class SkillCategory(StrEnum):
    DATA_ENGINEERING = "data_engineering"
    SQL = "sql"
    PYTHON = "python"
    CLOUD = "cloud"
    STREAMING = "streaming"
    MACHINE_LEARNING = "machine_learning"
    DEVOPS = "devops"
    SYSTEM_DESIGN = "system_design"
    SOFT_SKILLS = "soft_skills"
    OTHER = "other"


# Default skill list per category — used to pre-populate new assessments
DEFAULT_SKILLS: dict[SkillCategory, list[str]] = {
    SkillCategory.DATA_ENGINEERING: [
        "Apache Spark",
        "dbt",
        "Airflow",
        "Kafka",
        "Data Modeling",
    ],
    SkillCategory.SQL: [
        "Query Optimization",
        "Window Functions",
        "CTEs",
        "Indexing",
        "Data Warehousing",
    ],
    SkillCategory.PYTHON: ["OOP", "Testing", "Async", "Type Hints", "Performance"],
    SkillCategory.CLOUD: ["AWS", "GCP", "Azure", "Terraform", "Docker/K8s"],
    SkillCategory.STREAMING: [
        "Kafka",
        "Flink",
        "Spark Streaming",
        "Exactly-Once",
        "Schema Registry",
    ],
    SkillCategory.MACHINE_LEARNING: [
        "Feature Engineering",
        "Model Training",
        "MLflow",
        "Deployment",
        "Monitoring",
    ],
    SkillCategory.DEVOPS: [
        "CI/CD",
        "Git",
        "Monitoring",
        "Incident Response",
        "Security",
    ],
    SkillCategory.SYSTEM_DESIGN: [
        "Scalability",
        "Reliability",
        "APIs",
        "Caching",
        "Data Architecture",
    ],
    SkillCategory.SOFT_SKILLS: [
        "Communication",
        "Estimation",
        "Stakeholder Mgmt",
        "Code Review",
        "Mentoring",
    ],
}


class SkillRating(BaseModel):
    """A single skill rating within a snapshot."""

    skill: str
    category: SkillCategory = SkillCategory.OTHER
    rating: int = 5  # 1–10
    notes: str = ""

    @field_validator("rating")
    @classmethod
    def clamp_rating(cls, v: int) -> int:
        return max(1, min(10, v))


class SkillSnapshot(BaseModel):
    """A point-in-time skill self-assessment."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ratings: list[SkillRating] = Field(default_factory=list)
    notes: str = ""  # Overall reflection
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def skill_count(self) -> int:
        return len(self.ratings)

    @property
    def average_rating(self) -> float:
        if not self.ratings:
            return 0.0
        return sum(r.rating for r in self.ratings) / len(self.ratings)

    def rating_for(self, skill: str) -> int | None:
        """Return rating for a specific skill name, or None if not rated."""
        for r in self.ratings:
            if r.skill.lower() == skill.lower():
                return r.rating
        return None

    def weakest(self, n: int = 3) -> list[SkillRating]:
        """Return n lowest-rated skills."""
        return sorted(self.ratings, key=lambda r: r.rating)[:n]

    def strongest(self, n: int = 3) -> list[SkillRating]:
        """Return n highest-rated skills."""
        return sorted(self.ratings, key=lambda r: r.rating, reverse=True)[:n]


class SkillDelta(BaseModel):
    """Comparison of a single skill between two snapshots."""

    skill: str
    category: SkillCategory
    previous_rating: int
    current_rating: int
    delta: int  # current - previous
    trend: Literal["up", "down", "same"]

    @classmethod
    def compute(
        cls,
        skill: str,
        category: SkillCategory,
        previous: int,
        current: int,
    ) -> SkillDelta:
        delta = current - previous
        if delta > 0:
            trend: Literal["up", "down", "same"] = "up"
        elif delta < 0:
            trend = "down"
        else:
            trend = "same"
        return cls(
            skill=skill,
            category=category,
            previous_rating=previous,
            current_rating=current,
            delta=delta,
            trend=trend,
        )
