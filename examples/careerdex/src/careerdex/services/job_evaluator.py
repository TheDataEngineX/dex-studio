"""Job evaluator — orchestrates the full evaluation pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog

from careerdex.models.evaluation import Archetype, EvaluationScore, JobEvaluation
from careerdex.services.archetypes import detect_archetype
from careerdex.services.scoring import ScoringEngine

logger = structlog.get_logger()

__all__ = ["JobEvaluator", "evaluate_job"]


class JobEvaluator:
    """Orchestrates the job evaluation pipeline."""

    def __init__(self, cv_text: str | None = None):
        self.cv_text = cv_text
        self.scoring_engine = ScoringEngine(cv_text)

    def _extract_company_role(self, job_description: str) -> tuple[str, str]:
        """Extract company and role from description."""
        lines = job_description.strip().split("\n")
        role = lines[0][:100] if lines else "Unknown Role"

        company = "Unknown Company"
        for line in lines[:5]:
            if "company:" in line.lower():
                company = line.split(":", 1)[1].strip()
                break

        return company, role

    def _build_report(
        self,
        job_description: str,
        archetype: Archetype,
        scores: list[EvaluationScore],
        grade: str,
    ) -> dict[str, Any]:
        """Build the 6-block report."""
        return {
            "block_a_role_summary": {
                "archetype": archetype.value,
                "domain": "AI/ML" if "llm" in job_description.lower() else "Software",
                "seniority": "Senior" if "senior" in job_description.lower() else "Mid",
                "remote": "Remote" if "remote" in job_description.lower() else "On-site",
            },
            "block_b_cv_match": {
                "matching_keywords": ["Python", "ML"],
                "gaps": ["Kubernetes"],
                "mitigation": "Can learn on job",
            },
            "block_c_level_strategy": {
                "detected_level": "Senior",
                "positioning": "Emphasize delivery experience",
                "negotiation_tips": ["Highlight technical breadth"],
            },
            "block_d_compensation": {
                "market_data": "Not available",
                "recommendation": "Ask in first call",
            },
            "block_e_personalization": {
                "cv_changes": ["Add ML projects section"],
                "linkedin_changes": ["Update headline with AI/ML"],
            },
            "block_f_interview_prep": {
                "recommended_stories": ["Led migration", "Built ML pipeline"],
                "red_flags": ["Why leaving current role?"],
            },
        }

    def evaluate(
        self,
        job_description: str,
        job_url: str | None = None,
    ) -> JobEvaluation:
        """Run full evaluation pipeline."""
        archetype, confidence = detect_archetype(job_description)

        scores = self.scoring_engine.score_all(job_description, archetype)

        overall_score, grade = self.scoring_engine.calculate_overall(scores)

        company, role = self._extract_company_role(job_description)

        report = self._build_report(job_description, archetype, scores, grade)

        return JobEvaluation(
            id=str(uuid.uuid4()),
            company=company,
            role=role,
            archetype=archetype,
            overall_score=overall_score,
            overall_grade=grade,
            scores=scores,
            report=report,
            created_at=datetime.now(),
            cv_text=self.cv_text,
            job_description=job_description,
            job_url=job_url,
        )


def evaluate_job(
    job_description: str,
    cv_text: str | None = None,
    job_url: str | None = None,
) -> JobEvaluation:
    """Convenience function to evaluate a job."""
    evaluator = JobEvaluator(cv_text)
    return evaluator.evaluate(job_description, job_url)
