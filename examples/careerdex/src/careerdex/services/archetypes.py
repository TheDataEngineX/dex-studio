"""Archetype detection — classifies job roles into archetypes."""

from __future__ import annotations

from careerdex.models.evaluation import Archetype

__all__ = ["detect_archetype", "ARCHETYPE_PATTERNS"]

ARCHETYPE_PATTERNS: dict[Archetype, list[str]] = {
    Archetype.LLM_OPS: [
        "llmops",
        "llm ops",
        "ml platform",
        "ml pipeline",
        "model serving",
        "model deployment",
        "ml infrastructure",
        "eval",
        "evaluation pipeline",
        "feature store",
        "ml observability",
        "kubeflow",
        "mlflow",
    ],
    Archetype.AGENTIC: [
        "agent",
        "multi-agent",
        "agentic",
        "orchestration",
        "langchain",
        "autogen",
        "crewai",
        "human-in-the-loop",
        "hitl",
        "tool use",
        "function calling",
        "reAct",
        "autonomous",
    ],
    Archetype.PRODUCT_MANAGER: [
        "product manager",
        "product owner",
        "pm",
        "roadmap",
        "discovery",
        "kpi",
        "okr",
        "metrics",
        "stakeholder",
        "roadmapping",
    ],
    Archetype.SOLUTIONS_ARCHITECT: [
        "solutions architect",
        "system architect",
        "enterprise architect",
        "presales",
        "technical sales",
        "integration",
        "api design",
        "architecture review",
        "technical design",
    ],
    Archetype.DELIVERY_ENGINEER: [
        "delivery",
        "full-stack",
        "fullstack",
        "backend",
        "frontend",
        "client-facing",
        "consultant",
        "implementation",
        "sprint",
    ],
    Archetype.TRANSFORMATION: [
        "transformation",
        "change management",
        "adoption",
        "migration",
        "modernization",
        "technical lead",
        "staff engineer",
        "principal",
    ],
}


def detect_archetype(job_description: str) -> tuple[Archetype, float]:
    """Detect the archetype from job description.

    Returns:
        Tuple of (detected_archetype, confidence_score)
    """
    text = job_description.lower()

    scores: dict[Archetype, int] = {a: 0 for a in Archetype}

    for archetype, keywords in ARCHETYPE_PATTERNS.items():
        for keyword in keywords:
            if keyword in text:
                scores[archetype] += 1

    if not scores or max(scores.values()) == 0:
        return Archetype.DELIVERY_ENGINEER, 0.5

    best = max(scores.items(), key=lambda x: x[1])[0]
    confidence = min(scores[best] / 5.0, 1.0) if scores[best] > 0 else 0.5

    return best, confidence
