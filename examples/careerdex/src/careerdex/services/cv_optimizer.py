"""CV optimizer - extracts JD keywords and optimizes CV for ATS."""

from __future__ import annotations

import re
from typing import Any

from careerdex.models.resume import Resume

__all__ = ["CVOptimizer", "extract_keywords", "optimize_cv"]


TECH_KEYWORDS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "rust",
    "sql",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "terraform",
    "ci/cd",
    "devops",
    "ml",
    "ai",
    "llm",
    "nlp",
    "computer vision",
    "tensorflow",
    "pytorch",
    "pandas",
    "spark",
    "hadoop",
    "kafka",
    "redis",
    "postgresql",
    "mongodb",
    "graphql",
    "rest",
    "api",
]

SOFT_KEYWORDS = [
    "leadership",
    "team management",
    "stakeholder",
    "communication",
    "problem-solving",
    "agile",
    "scrum",
    "project management",
    "mentoring",
    "cross-functional",
]


def extract_keywords(job_description: str) -> list[dict[str, Any]]:
    """Extract keywords from job description with categories."""
    text_lower = job_description.lower()
    keywords: list[dict[str, Any]] = []

    for kw in TECH_KEYWORDS:
        if kw.lower() in text_lower:
            keywords.append(
                {"keyword": kw, "category": "technical", "count": text_lower.count(kw.lower())}
            )

    for kw in SOFT_KEYWORDS:
        if kw.lower() in text_lower:
            keywords.append(
                {"keyword": kw, "category": "soft", "count": text_lower.count(kw.lower())}
            )

    requirements_match = re.search(
        r"requirements?[:\s]+(.*?)(?:responsibilities|qualifications|benefits|$)",
        text_lower,
        re.IGNORECASE | re.DOTALL,
    )
    if requirements_match:
        req_text = requirements_match.group(1)
        words: list[str] = re.findall(r"\b\w+\b", req_text)
        for word in words:
            if len(word) > 3 and word.lower() not in [k["keyword"].lower() for k in keywords]:
                keywords.append({"keyword": word, "category": "skill", "count": 1})

    return sorted(keywords, key=lambda x: x["count"], reverse=True)


def detect_language(job_description: str) -> str:
    """Detect language from JD."""
    spanish_words = ["desarrollador", "ingeniero", "experiencia", "requisitos", "beneficios"]
    if any(w in job_description.lower() for w in spanish_words):
        return "es"
    return "en"


def detect_format(job_description: str) -> str:
    """Detect paper format from company location."""
    if any(
        loc in job_description.lower() for loc in ["usa", "united states", "canada", "us-based"]
    ):
        return "letter"
    return "a4"


class CVOptimizer:
    """Optimize CV for specific job description."""

    def __init__(self, resume: Resume):
        self.resume = resume

    def optimize(self, job_description: str) -> dict[str, Any]:
        """Optimize CV for the job description."""
        keywords = extract_keywords(job_description)
        language = detect_language(job_description)
        paper_format = detect_format(job_description)

        optimized_summary = self._generate_summary(keywords, language)
        reordered_experience = self._reorder_experience(keywords)
        competencies = self._generate_competencies(keywords)

        return {
            "keywords": keywords[:20],
            "language": language,
            "paper_format": paper_format,
            "optimized_summary": optimized_summary,
            "reordered_experience": reordered_experience,
            "competencies": competencies,
            "keyword_coverage": self._calculate_coverage(keywords),
        }

    def _generate_summary(self, keywords: list[dict[str, Any]], language: str) -> str:
        """Generate optimized professional summary."""
        top_keywords = [k["keyword"] for k in keywords[:5]]
        kw_str = ", ".join(top_keywords)

        if language == "es":
            return f"Profesional con experiencia en {kw_str}. "
            "Orientado a resultados con capacidad de liderar proyectos."

        return f"Professional with hands-on experience in {kw_str}. "
        "Results-driven with proven ability to lead technical initiatives."

    def _reorder_experience(self, keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Reorder experience by JD relevance."""
        keyword_set = set(k["keyword"].lower() for k in keywords)

        def count_matches(exp: dict[str, Any]) -> int:
            title = exp.get("title", "")
            company = exp.get("company", "")
            bullets = " ".join(exp.get("bullets", []))
            text = f"{title} {company} {bullets}"
            return sum(1 for kw in keyword_set if kw in text.lower())

        result: list[dict[str, Any]] = [
            {
                "title": e.title,
                "company": e.company,
                "bullets": e.bullets,
            }
            for e in (self.resume.experience or [])
        ]
        return result

    def _generate_competencies(self, keywords: list[dict[str, Any]]) -> list[str]:
        """Generate competency grid from keywords."""
        tech = [k["keyword"] for k in keywords if k["category"] == "technical"][:4]
        soft = [k["keyword"] for k in keywords if k["category"] == "soft"][:2]
        return tech + soft

    def _calculate_coverage(self, keywords: list[dict[str, Any]]) -> float:
        """Calculate keyword coverage percentage."""
        cv_text = " ".join(
            [
                self.resume.summary or "",
                " ".join(
                    [e.title + " " + " ".join(e.bullets) for e in (self.resume.experience or [])]
                ),
                " ".join([s.category for s in (self.resume.skills or [])]),
            ]
        ).lower()

        matched = sum(1 for k in keywords[:15] if k["keyword"].lower() in cv_text)
        return round((matched / 15) * 100, 1) if keywords else 0.0


def optimize_cv(resume: Resume, job_description: str) -> dict[str, Any]:
    """Convenience function to optimize CV for a job."""
    optimizer = CVOptimizer(resume)
    return optimizer.optimize(job_description)
