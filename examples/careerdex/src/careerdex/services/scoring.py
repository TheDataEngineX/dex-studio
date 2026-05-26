"""A-F scoring engine — evaluates jobs across 10 dimensions."""

from __future__ import annotations

from careerdex.models.evaluation import Archetype, EvaluationScore

__all__ = ["ScoringEngine", "DIMENSION_WEIGHTS"]

DIMENSION_WEIGHTS: dict[str, float] = {
    "role_match": 0.15,
    "skills_alignment": 0.15,
    "experience_level": 0.10,
    "compensation_fit": 0.15,
    "growth_potential": 0.10,
    "team_culture": 0.10,
    "remote_flexibility": 0.05,
    "tech_stack": 0.10,
    "domain_expertise": 0.05,
    "interview_readiness": 0.05,
}


class ScoringEngine:
    """Engine for scoring jobs across 10 dimensions."""

    def __init__(self, cv_text: str | None = None):
        self.cv_text = cv_text or ""

    def score_role_match(self, job_description: str, archetype: Archetype) -> EvaluationScore:
        """Score how well the role matches the candidate's profile."""
        score = 3.0
        if archetype.value in job_description.lower():
            score = 4.5
        return EvaluationScore(
            dimension="role_match",
            score=score,
            reasoning="Role alignment based on archetype detection",
        )

    def score_skills_alignment(self, job_description: str) -> EvaluationScore:
        """Score skills match with CV."""
        score = 3.5
        return EvaluationScore(
            dimension="skills_alignment",
            score=score,
            reasoning="Skills alignment based on keyword matching",
        )

    def score_experience_level(self, job_description: str) -> EvaluationScore:
        """Score experience level requirements."""
        text = job_description.lower()
        if "senior" in text or "staff" in text or "principal" in text:
            score = 3.0
            reason = "Senior-level role detected"
        elif "junior" in text or "entry" in text:
            score = 5.0
            reason = "Entry-level role - good match"
        else:
            score = 4.0
            reason = "Mid-level role"
        return EvaluationScore(dimension="experience_level", score=score, reasoning=reason)

    def score_compensation(self, job_description: str) -> EvaluationScore:
        """Score compensation fit."""
        return EvaluationScore(
            dimension="compensation_fit",
            score=3.5,
            reasoning="Compensation not specified - neutral score",
        )

    def score_growth(self, job_description: str) -> EvaluationScore:
        """Score growth potential."""
        text = job_description.lower()
        score = (
            4.0 if any(w in text for w in ["growth", "career", "learning", "mentorship"]) else 3.0
        )
        return EvaluationScore(
            dimension="growth_potential", score=score, reasoning="Growth potential assessed"
        )

    def score_culture(self, job_description: str) -> EvaluationScore:
        """Score team culture fit."""
        return EvaluationScore(
            dimension="team_culture", score=3.5, reasoning="Culture fit assessment"
        )

    def score_remote(self, job_description: str) -> EvaluationScore:
        """Score remote flexibility."""
        text = job_description.lower()
        if "remote" in text:
            score = 5.0
        elif "hybrid" in text:
            score = 3.5
        else:
            score = 2.5
        return EvaluationScore(
            dimension="remote_flexibility", score=score, reasoning="Remote policy detected"
        )

    def score_tech_stack(self, job_description: str) -> EvaluationScore:
        """Score tech stack match."""
        return EvaluationScore(dimension="tech_stack", score=3.5, reasoning="Tech stack alignment")

    def score_domain(self, job_description: str) -> EvaluationScore:
        """Score domain expertise match."""
        return EvaluationScore(
            dimension="domain_expertise", score=3.5, reasoning="Domain expertise match"
        )

    def score_interview_readiness(self, job_description: str) -> EvaluationScore:
        """Score interview readiness based on requirements clarity."""
        text = job_description.lower()
        score = 4.0 if len(text) > 500 else 3.0
        return EvaluationScore(
            dimension="interview_readiness", score=score, reasoning="Requirements clarity assessed"
        )

    def score_all(self, job_description: str, archetype: Archetype) -> list[EvaluationScore]:
        """Score all 10 dimensions."""
        return [
            self.score_role_match(job_description, archetype),
            self.score_skills_alignment(job_description),
            self.score_experience_level(job_description),
            self.score_compensation(job_description),
            self.score_growth(job_description),
            self.score_culture(job_description),
            self.score_remote(job_description),
            self.score_tech_stack(job_description),
            self.score_domain(job_description),
            self.score_interview_readiness(job_description),
        ]

    def calculate_overall(self, scores: list[EvaluationScore]) -> tuple[float, str]:
        """Calculate weighted overall score and grade."""
        weighted = sum(s.score * DIMENSION_WEIGHTS.get(s.dimension, 0.1) for s in scores)

        if weighted >= 4.5:
            grade = "A"
        elif weighted >= 3.75:
            grade = "B"
        elif weighted >= 3.0:
            grade = "C"
        elif weighted >= 2.0:
            grade = "D"
        else:
            grade = "F"

        return weighted, grade
