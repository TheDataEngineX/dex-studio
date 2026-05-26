"""RAG evaluation models and service."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EvaluationMetric(StrEnum):
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_RECALL = "context_recall"
    CONTEXT_PRECISION = "context_precision"
    CONTEXTRelevance = "context_relevance"
    ANSWER_SIMILARITY = "answer_similarity"
    ANSWER_CORRECTNESS = "answer_correctness"
    BLEU = "bleu"
    ROUGE = "rouge"
    RAGAS = "ragas"


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TestCase(BaseModel):
    """A single test case for RAG evaluation."""

    id: str
    question: str
    ground_truth_answer: str
    context: list[str] = Field(default_factory=list)
    retrieved_context: list[str] = Field(default_factory=list)
    generated_answer: str = ""
    scores: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class EvaluationRun(BaseModel):
    """An evaluation run for a RAG system."""

    id: str
    name: str
    description: str = ""
    metrics: list[EvaluationMetric] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    status: EvaluationStatus = EvaluationStatus.PENDING
    average_scores: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class RAGMetrics(BaseModel):
    """Comprehensive RAG metrics."""

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_recall: float = 0.0
    context_precision: float = 0.0
    context_relevance: float = 0.0
    answer_similarity: float = 0.0
    overall_score: float = 0.0


class EvaluationSummary(BaseModel):
    """Summary of an evaluation run."""

    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_scores: dict[str, float]
    best_case: str | None
    worst_case: str | None
    recommendations: list[str] = Field(default_factory=list)
