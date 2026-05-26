"""Company research service — LLM-powered deep research on companies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import structlog

from careerdex.services.llm_provider import LLMConfig, LLMProvider

logger = structlog.get_logger()

__all__ = [
    "CompanyResearch",
    "research_company",
    "research_company_with_llm",
    "build_research_prompt",
]


class CompanySize(StrEnum):
    STARTUP = "startup"
    SMB = "smb"
    MID_MARKET = "mid_market"
    ENTERPRISE = "enterprise"


class FundingStage(StrEnum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    IPO = "ipo"


@dataclass
class CompanyResearch:
    """Deep research data for a company."""

    name: str
    website: str
    description: str
    industry: str
    size: CompanySize
    funding_stage: FundingStage | None
    founded_year: int | None
    headquarters: str
    culture_notes: str
    tech_stack: list[str]
    products: list[str]
    competitors: list[str]
    recent_news: list[str]
    red_flags: list[str]
    green_flags: list[str]
    interview_difficulty: str
    interview_tips: list[str]
    research_date: datetime
    analysis_mode: str = "keyword"  # "keyword" | "ai"
    prompt_used: str = ""


def build_research_prompt(company_name: str) -> str:
    return f"""You are a senior career strategist helping a data engineering / AI/ML professional
prepare for job interviews. Research "{company_name}" based on your training knowledge.

Provide a structured JSON response (no markdown, no explanation — JSON only):
{{
  "description": "2-3 sentence factual company overview",
  "industry": "primary industry vertical",
  "size": "startup|smb|mid_market|enterprise",
  "funding_stage": "pre_seed|seed|series_a|series_b|series_c|ipo|null",
  "founded_year": 2010,
  "headquarters": "City, State/Country",
  "culture_notes": "2-3 sentences on work culture, pace, and environment based on known data",
  "tech_stack": ["Python", "Kubernetes", "Spark"],
  "products": ["Product A — one line description"],
  "competitors": ["Competitor A", "Competitor B"],
  "recent_news": ["Notable development 1", "Notable development 2"],
  "red_flags": ["Specific concern based on known public information"],
  "green_flags": ["Specific strength based on known public information"],
  "interview_difficulty": "Easy|Medium|Hard",
  "interview_tips": [
    "Tip grounded in their known tech stack or culture",
    "What to emphasize given their domain",
    "Questions to ask them that show deep understanding"
  ]
}}

Base ALL information on your training data. If you lack specific knowledge about this company,
clearly state "Limited public information available" in the description and provide general
industry context. Output ONLY valid JSON."""


async def research_company_with_llm(company_name: str, llm_config: LLMConfig) -> CompanyResearch:
    """Research a company using LLM. Falls back to keyword stub on parse failure."""
    logger.info("company_research_llm_started", company=company_name, provider=llm_config.provider)
    prompt = build_research_prompt(company_name)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a company research assistant. "
                "Respond with valid JSON only — no markdown, no explanation."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    raw = await LLMProvider.chat(llm_config, messages)
    data = _parse_json_response(raw)

    size_val = str(data.get("size", "startup"))
    size = (
        CompanySize(size_val) if size_val in CompanySize._value2member_map_ else CompanySize.STARTUP
    )

    fs_val = data.get("funding_stage")
    funding = (
        FundingStage(str(fs_val))
        if fs_val and str(fs_val) in FundingStage._value2member_map_
        else None
    )

    fy = data.get("founded_year")
    founded = int(str(fy)) if fy and str(fy).isdigit() else None

    return CompanyResearch(
        name=company_name,
        website=f"https://{company_name.lower().replace(' ', '')}.com",
        description=str(data.get("description", "")),
        industry=str(data.get("industry", "Technology")),
        size=size,
        funding_stage=funding,
        founded_year=founded,
        headquarters=str(data.get("headquarters", "")),
        culture_notes=str(data.get("culture_notes", "")),
        tech_stack=_as_str_list(data.get("tech_stack")),
        products=_as_str_list(data.get("products")),
        competitors=_as_str_list(data.get("competitors")),
        recent_news=_as_str_list(data.get("recent_news")),
        red_flags=_as_str_list(data.get("red_flags")),
        green_flags=_as_str_list(data.get("green_flags")),
        interview_difficulty=str(data.get("interview_difficulty", "Medium")),
        interview_tips=_as_str_list(data.get("interview_tips")),
        research_date=datetime.now(),
        analysis_mode="ai",
        prompt_used=prompt,
    )


def research_company(company_name: str) -> CompanyResearch:
    """Keyword-mode stub — used when LLM is offline."""
    logger.info("company_research_keyword_fallback", company=company_name)
    return CompanyResearch(
        name=company_name,
        website=f"https://{company_name.lower().replace(' ', '')}.com",
        description=f"{company_name} — connect an AI provider for detailed research.",
        industry="Technology",
        size=CompanySize.STARTUP,
        funding_stage=None,
        founded_year=None,
        headquarters="Unknown",
        culture_notes="Connect an AI provider in Settings to get culture insights.",
        tech_stack=[],
        products=[],
        competitors=[],
        recent_news=[],
        red_flags=[],
        green_flags=[],
        interview_difficulty="Medium",
        interview_tips=["Connect an AI provider for tailored interview tips."],
        research_date=datetime.now(),
        analysis_mode="keyword",
        prompt_used="",
    )


def _parse_json_response(raw: str) -> dict[str, object]:
    """Extract and parse JSON from LLM response."""
    text = raw.strip()
    # Strip markdown fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        logger.warning("research_json_parse_failed", raw_snippet=text[:200])
        return {}


def _as_str_list(val: object) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    return []
