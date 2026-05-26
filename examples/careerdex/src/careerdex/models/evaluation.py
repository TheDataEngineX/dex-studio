"""Evaluation data models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Archetype(StrEnum):
    LLM_OPS = "llm_ops"
    AGENTIC = "agentic"
    PRODUCT_MANAGER = "product_manager"
    SOLUTIONS_ARCHITECT = "solutions_architect"
    DELIVERY_ENGINEER = "delivery_engineer"
    TRANSFORMATION = "transformation"


class EvaluationScore(BaseModel):
    dimension: str
    score: float
    reasoning: str


class JobEvaluation(BaseModel):
    id: str
    company: str
    role: str
    archetype: Archetype
    overall_score: float
    overall_grade: str
    scores: list[EvaluationScore]
    report: dict[str, Any]
    created_at: datetime
    cv_text: str | None = None
    job_description: str | None = None
    job_url: str | None = None
