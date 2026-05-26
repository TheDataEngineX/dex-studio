"""Resume matcher service — compares resume against job descriptions.

Supports multi-provider LLM (Ollama, OpenAI, Anthropic, Groq) with keyword fallback.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field

import structlog

from careerdex.models.resume import Resume
from careerdex.services.llm_provider import LLMConfig, LLMProvider

logger = structlog.get_logger()

__all__ = ["ResumeMatcher", "MatchResult", "SuggestedEdit", "SuggestedEdits"]


@dataclass
class SuggestedEdit:
    """One targeted improvement to a resume section."""

    section: str  # "summary" | "skills" | "experience" | "general"
    original: str  # current text (empty for additions)
    suggested: str  # replacement / addition
    reason: str  # why this helps match the JD
    impact: str = "medium"  # "high" | "medium" | "low"


@dataclass
class SuggestedEdits:
    """AI-generated resume edits targeted to a specific job description."""

    summary_rewrite: str  # New professional summary for this role
    skill_additions: list[str]  # Skills to add or highlight
    bullet_improvements: list[SuggestedEdit]  # Per-bullet rewrites
    keyword_gaps: list[str]  # JD keywords absent from resume
    coaching_note: str  # 1-2 sentence strategic advice


@dataclass
class MatchResult:
    """Result of matching a resume against a job description."""

    overall_score: float  # 0–100 blended score
    skill_match_rate: float  # % of JD skills found in resume
    missing_skills: list[str]
    matched_skills: list[str]
    keyword_matches: list[tuple[str, int]]  # (keyword, count in resume)
    summary: str

    # Analysis metadata
    analysis_mode: str = "keyword"  # keyword | ai | ai_error

    # AI scoring dimensions — populated in AI mode
    experience_depth_score: float | None = None
    responsibility_alignment_score: float | None = None
    domain_context_score: float | None = None
    ats_score: float | None = None  # ATS keyword coverage %

    # AI qualitative output
    ai_insights: list[str] = field(default_factory=list)
    ai_gaps: list[str] = field(default_factory=list)
    recommendation: str = ""

    # Advanced fit signals
    seniority_fit: str = ""  # under-qualified | strong-fit | over-qualified
    culture_signals: list[str] = field(default_factory=list)  # detected culture keywords
    years_required: str = ""  # extracted from JD ("3-5 years")
    education_match: str = ""  # degree requirement vs resume

    # Error state
    ai_error: str | None = None

    # Transparency — prompt shown in UI
    prompt_used: str = ""

    # Edit suggestions — populated by get_suggested_edits()
    suggested_edits: SuggestedEdits | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (exposed so UI can display them)
# ─────────────────────────────────────────────────────────────────────────────


def build_analysis_prompt(resume_text: str, job_description: str) -> str:
    rec_options = (
        "Apply with confidence | Strong candidate | "
        "Good match with gaps | Partial match | Weak match"
    )
    return (
        "You are an expert technical recruiter for data engineering and AI/ML roles.\n"
        "Analyze the resume vs job description. Focus on REAL experience alignment —\n"
        "genuine hands-on depth and production scale, not just keyword presence.\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"RESUME (first 4000 chars):\n{resume_text[:4000]}\n\n"
        "Score each dimension 0–100:\n"
        "- experience_depth_score: Genuine hands-on use (quantified impact, prod systems)?\n"
        "- responsibility_alignment_score: Past duties match what this role needs?\n"
        "- domain_context_score: Industry/domain knowledge fit (scale, real-time, ML, cloud)?\n"
        "- ats_score: Keyword coverage for ATS parsing (0–100 % of JD terms present)?\n\n"
        "Also extract:\n"
        "- seniority_fit: 'under-qualified', 'strong-fit', or 'over-qualified'\n"
        "- culture_signals: list of culture keywords found (startup, enterprise, agile, etc.)\n"
        "- years_required: years of experience required stated in JD (e.g. '5+ years')\n"
        "- education_match: does education section meet the requirement?\n\n"
        "Return ONLY a valid JSON object (no markdown, no extra text):\n"
        '{"overall_score":0,"experience_depth_score":0,'
        '"responsibility_alignment_score":0,"domain_context_score":0,'
        '"ats_score":0,'
        '"insights":["strength1","strength2"],'
        '"gaps":["gap1","gap2"],'
        '"seniority_fit":"strong-fit",'
        '"culture_signals":["agile","data-driven"],'
        '"years_required":"3-5 years",'
        '"education_match":"matches",'
        f'"recommendation":"one of: {rec_options}"}}'
    )


def build_edits_prompt(
    resume_text: str,
    job_description: str,
    gaps: list[str],
    resume_name: str,
) -> str:
    gaps_str = ", ".join(gaps[:8]) if gaps else "none identified"
    return (
        "You are a senior technical career coach for data engineering and AI/ML roles,\n"
        "with 15+ years advising engineers at FAANG-scale and high-growth startups.\n\n"
        "A candidate needs targeted resume edits to better match a job description.\n"
        "Your suggestions must be grounded in REAL production experience patterns —\n"
        "quantified impact, specific technologies, proven scale. Do NOT fabricate;\n"
        "improve the framing of existing experience.\n\n"
        f"CANDIDATE: {resume_name}\n"
        f"TOP GAPS IDENTIFIED: {gaps_str}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:2000]}\n\n"
        f"CURRENT RESUME:\n{resume_text[:3000]}\n\n"
        "Provide improvements in this exact JSON format:\n"
        "{\n"
        '  "summary_rewrite": "3-sentence professional summary targeting THIS role exactly",\n'
        '  "skill_additions": ["Add Apache Iceberg to data lakehouse skills", "..."],\n'
        '  "bullet_improvements": [\n'
        "    {\n"
        '      "section": "experience",\n'
        '      "original": "Built data pipelines for processing customer data",\n'
        '      "suggested": "Designed Apache Spark pipelines processing 2TB/day of behavioral '
        'data with 99.9% SLA on AWS EMR, using Delta Lake for time-travel auditing",\n'
        '      "reason": "JD requires demonstrated production scale + specific lakehouse tech",\n'
        '      "impact": "high"\n'
        "    }\n"
        "  ],\n"
        '  "keyword_gaps": ["data contracts", "real-time CDC", "observability"],\n'
        '  "coaching_note": "1-2 strategic sentences on the most impactful change."\n'
        "}\n\n"
        "Return ONLY valid JSON. Be specific and production-realistic."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main service
# ─────────────────────────────────────────────────────────────────────────────


class ResumeMatcher:
    """Match resume against job descriptions — keyword and AI modes."""

    TECH_KEYWORDS = {
        "python",
        "java",
        "scala",
        "javascript",
        "typescript",
        "go",
        "rust",
        "c++",
        "c#",
        "sql",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "elasticsearch",
        "opensearch",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "terraform",
        "pulumi",
        "react",
        "angular",
        "vue",
        "node.js",
        "django",
        "flask",
        "fastapi",
        "spark",
        "pyspark",
        "hadoop",
        "kafka",
        "flink",
        "airflow",
        "prefect",
        "dagster",
        "dbt",
        "snowflake",
        "databricks",
        "delta lake",
        "apache iceberg",
        "hudi",
        "redshift",
        "athena",
        "glue",
        "kinesis",
        "emr",
        "bigquery",
        "synapse",
        "data lake",
        "lakehouse",
        "machine learning",
        "ml",
        "mlflow",
        "deep learning",
        "tensorflow",
        "pytorch",
        "keras",
        "scikit-learn",
        "xgboost",
        "nlp",
        "computer vision",
        "llm",
        "rag",
        "vector search",
        "faiss",
        "pinecone",
        "weaviate",
        "embedding",
        "gpt",
        "ollama",
        "langchain",
        "llamaindex",
        "git",
        "github",
        "ci/cd",
        "jenkins",
        "github actions",
        "rest",
        "api",
        "graphql",
        "grpc",
        "agile",
        "scrum",
        "jira",
        "linux",
        "bash",
        "shell",
        "data engineering",
        "etl",
        "elt",
        "data pipeline",
        "data quality",
        "data catalog",
        "data lineage",
        "data contracts",
        "sla",
        "tableau",
        "power bi",
        "looker",
        "metabase",
        "statistics",
        "a/b testing",
        "ab testing",
        "grafana",
        "prometheus",
        "opentelemetry",
        "datadog",
        "real-time",
        "streaming",
        "batch",
        "cdc",
        "debezium",
        "observability",
        "monitoring",
        "alerting",
    }

    def match_text(self, resume_text: str, job_description: str) -> MatchResult:
        """Keyword-only match — no LLM required."""
        resume_lower = resume_text.lower()
        job_keywords = self._extract_keywords(job_description)

        matched_skills: list[str] = []
        missing_skills: list[str] = []
        for skill in job_keywords:
            if skill in resume_lower:
                matched_skills.append(skill)
            else:
                missing_skills.append(skill)

        skill_match_rate = (len(matched_skills) / len(job_keywords) * 100) if job_keywords else 0.0

        keyword_counter: Counter[str] = Counter()
        for keyword in job_keywords:
            count = resume_lower.count(keyword)
            if count > 0:
                keyword_counter[keyword] = count
        keyword_matches = keyword_counter.most_common(15)

        overall_score = self._calculate_score(skill_match_rate, keyword_matches, len(job_keywords))
        ats = round(len(matched_skills) / max(len(job_keywords), 1) * 100, 1)
        years_req = _extract_years_required(job_description)

        return MatchResult(
            overall_score=overall_score,
            skill_match_rate=skill_match_rate,
            missing_skills=missing_skills[:20],
            matched_skills=matched_skills[:20],
            keyword_matches=keyword_matches,
            summary=self._generate_summary(
                overall_score, skill_match_rate, matched_skills, missing_skills
            ),
            analysis_mode="keyword",
            ats_score=ats,
            years_required=years_req,
        )

    async def match_with_ai(
        self,
        resume_text: str,
        job_description: str,
        llm_config: LLMConfig | None = None,
    ) -> MatchResult:
        """AI-powered semantic match. Falls back to keyword on LLM error.

        Returns full MatchResult with prompt_used set for UI transparency.
        """
        baseline = self.match_text(resume_text, job_description)
        cfg = llm_config or LLMConfig()
        prompt = build_analysis_prompt(resume_text, job_description)

        try:
            raw = await LLMProvider.chat(cfg, [{"role": "user", "content": prompt}])
            ai = _parse_json(raw)

            def _f(key: str, fallback: float = 0.0) -> float:
                val = ai.get(key)
                return float(val) if val is not None else fallback  # type: ignore[arg-type]

            def _l(key: str) -> list[str]:
                val = ai.get(key)
                return [str(x) for x in val] if isinstance(val, list) else []

            def _s(key: str) -> str:
                return str(ai.get(key) or "")

            ai_score = _f("overall_score", baseline.overall_score)
            # 70% AI semantic + 30% keyword for robustness against hallucination
            blended = round(ai_score * 0.7 + baseline.overall_score * 0.3, 1)

            logger.debug(
                "ai_match_complete",
                provider=cfg.provider,
                model=cfg.model,
                ai_score=ai_score,
                blended=blended,
            )
            return MatchResult(
                overall_score=blended,
                skill_match_rate=baseline.skill_match_rate,
                missing_skills=baseline.missing_skills,
                matched_skills=baseline.matched_skills,
                keyword_matches=baseline.keyword_matches,
                summary=self._generate_summary(
                    blended,
                    baseline.skill_match_rate,
                    baseline.matched_skills,
                    baseline.missing_skills,
                ),
                analysis_mode="ai",
                experience_depth_score=_f("experience_depth_score"),
                responsibility_alignment_score=_f("responsibility_alignment_score"),
                domain_context_score=_f("domain_context_score"),
                ats_score=_f("ats_score", baseline.ats_score or 0.0),
                ai_insights=_l("insights"),
                ai_gaps=_l("gaps"),
                recommendation=_s("recommendation"),
                seniority_fit=_s("seniority_fit"),
                culture_signals=_l("culture_signals"),
                years_required=_s("years_required") or baseline.years_required,
                education_match=_s("education_match"),
                prompt_used=prompt,
            )

        except Exception as exc:
            logger.warning("ai_match_failed", provider=cfg.provider, error=str(exc))
            fields = {
                **baseline.__dict__,
                "analysis_mode": "ai_error",
                "ai_error": str(exc),
                "prompt_used": prompt,
            }
            return MatchResult(**fields)

    async def get_suggested_edits(
        self,
        resume_text: str,
        job_description: str,
        result: MatchResult,
        llm_config: LLMConfig | None = None,
        resume_name: str = "Candidate",
    ) -> SuggestedEdits:
        """Generate production-grounded resume edit suggestions for this specific JD."""
        cfg = llm_config or LLMConfig()
        prompt = build_edits_prompt(
            resume_text, job_description, result.ai_gaps or result.missing_skills, resume_name
        )

        try:
            raw = await LLMProvider.chat(cfg, [{"role": "user", "content": prompt}])
            ai = _parse_json(raw)

            def _s(key: str) -> str:
                return str(ai.get(key) or "")

            def _l(key: str) -> list[str]:
                val = ai.get(key)
                return [str(x) for x in val] if isinstance(val, list) else []

            raw_bullets = ai.get("bullet_improvements", [])
            bullets: list[SuggestedEdit] = []
            if isinstance(raw_bullets, list):
                for b in raw_bullets:
                    if not isinstance(b, dict):
                        continue
                    bullets.append(
                        SuggestedEdit(
                            section=str(b.get("section", "experience")),
                            original=str(b.get("original", "")),
                            suggested=str(b.get("suggested", "")),
                            reason=str(b.get("reason", "")),
                            impact=str(b.get("impact", "medium")),
                        )
                    )

            return SuggestedEdits(
                summary_rewrite=_s("summary_rewrite"),
                skill_additions=_l("skill_additions"),
                bullet_improvements=bullets,
                keyword_gaps=_l("keyword_gaps"),
                coaching_note=_s("coaching_note"),
            )

        except Exception as exc:
            logger.warning("suggested_edits_failed", error=str(exc))
            return SuggestedEdits(
                summary_rewrite="",
                skill_additions=result.missing_skills[:5],
                bullet_improvements=[],
                keyword_gaps=result.missing_skills,
                coaching_note=f"AI edit suggestions unavailable: {exc}",
            )

    # Structured resume (legacy path)
    def match(self, resume: Resume, job_description: str) -> MatchResult:
        return self.match_text(self.resume_to_text(resume), job_description)

    def resume_to_text(self, resume: Resume) -> str:
        """Flatten Resume model to plain text for matching."""
        parts: list[str] = []
        if resume.contact.name:
            parts.append(f"{resume.contact.name} {resume.contact.title}")
        if resume.summary:
            parts.append(resume.summary)
        for group in resume.skills:
            parts.extend(group.skills)
        for exp in resume.experience:
            parts += [exp.company, exp.title, *exp.bullets, *exp.technologies]
        for proj in resume.projects:
            parts += [proj.name, proj.description, *proj.technologies, *proj.highlights]
        for cert in resume.certifications:
            parts.append(cert.name)
        for edu in resume.education:
            parts += [edu.degree, edu.field, *edu.relevant_coursework]
        return " ".join(parts)

    # ── internal ──────────────────────────────────────────────────────────── #

    def _extract_keywords(self, text: str) -> list[str]:
        text_lower = text.lower()
        found: list[str] = [kw for kw in self.TECH_KEYWORDS if kw in text_lower]
        # bonus pass: skills section
        sec_match = re.search(
            r"(?:required|preferred|must have|experience with|skills?:?)(.*?)(?=\n\n|\Z)",
            text_lower,
            re.DOTALL,
        )
        if sec_match:
            sec = sec_match.group(1)
            for kw in self.TECH_KEYWORDS:
                if kw in sec and kw not in found:
                    found.append(kw)
        return list(set(found))

    def _calculate_score(
        self,
        skill_match_rate: float,
        keyword_matches: list[tuple[str, int]],
        total_keywords: int,
    ) -> float:
        if total_keywords == 0:
            return 50.0
        kw_coverage = len(keyword_matches) / total_keywords
        score = skill_match_rate * 0.6 + kw_coverage * 100 * 0.3 + 10.0
        return min(max(score, 0.0), 100.0)

    def _generate_summary(
        self,
        overall_score: float,
        keyword_score: float,
        matched_skills: list[str],
        missing_skills: list[str],
    ) -> str:
        label = (
            "Strong match"
            if overall_score >= 80
            else "Good match"
            if overall_score >= 60
            else "Moderate match"
            if overall_score >= 40
            else "Weak match"
        )
        parts = [f"{label} ({overall_score:.0f}%)"]
        if matched_skills:
            parts.append(f"Matched: {', '.join(matched_skills[:5])}")
        if missing_skills:
            parts.append(f"Missing: {', '.join(missing_skills[:5])}")
        return ". ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_json(raw: str) -> dict[str, object]:
    """Extract and parse JSON from LLM response, tolerating fences and stray text."""
    if "```" in raw:
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        return dict(json.loads(raw))
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if m:
        return dict(json.loads(m.group()))
    raise ValueError(f"No valid JSON found in response: {raw[:200]}")


def _extract_years_required(jd: str) -> str:
    """Heuristic extraction of experience requirement from JD text."""
    patterns = [
        r"(\d+\+?\s*[-–to]+\s*\d+\s*years?)",
        r"(\d+\+\s*years?)",
        r"(\d+\s*years?\s+of\s+experience)",
        r"(minimum\s+\d+\s*years?)",
    ]
    for pat in patterns:
        m = re.search(pat, jd, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""
