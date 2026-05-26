"""Cover letter generator service — AI-powered, per-job personalized cover letters."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog

_log = structlog.get_logger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/chat"
_MODEL = "llama3.2"

_COVER_LETTER_PROMPT = """You are an expert career coach and professional writer.

Write a compelling, personalized cover letter for the following job application.

**Candidate Resume Summary:**
{resume_summary}

**Job Title:** {job_title}
**Company:** {company}
**Job Description:**
{job_description}

**Instructions:**
- Write 3-4 paragraphs (opening, skills match, why this company, call to action)
- Match specific skills from the job description to the candidate's experience
- Sound genuine and specific — not generic
- Professional but not stiff
- Around 250-350 words
- Do NOT include the date, address, or salutation header — just the body paragraphs

Write the cover letter body:"""


@dataclass
class CoverLetterResult:
    """Result of cover letter generation."""

    job_title: str
    company: str
    content: str
    word_count: int
    model_used: str
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error


class CoverLetterService:
    """Generate AI-powered cover letters using Ollama."""

    def __init__(self, model: str = _MODEL, ollama_url: str = _OLLAMA_URL) -> None:
        self._model = model
        self._url = ollama_url

    def generate(
        self,
        job_title: str,
        company: str,
        job_description: str,
        resume_summary: str,
        temperature: float = 0.7,
    ) -> CoverLetterResult:
        """Generate a cover letter for the given job.

        Falls back gracefully if Ollama is offline.
        """
        prompt = _COVER_LETTER_PROMPT.format(
            resume_summary=resume_summary[:1500],
            job_title=job_title,
            company=company,
            job_description=job_description[:2000],
        )

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional cover letter writer. "
                        "Write only the cover letter body."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 600},
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(self._url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = str(data.get("message", {}).get("content", "")).strip()

                if not content:
                    return CoverLetterResult(
                        job_title=job_title,
                        company=company,
                        content="",
                        word_count=0,
                        model_used=self._model,
                        error="Empty response from model.",
                    )

                word_count = len(re.findall(r"\w+", content))
                _log.info(
                    "cover_letter_generated",
                    job=job_title,
                    company=company,
                    words=word_count,
                )

                return CoverLetterResult(
                    job_title=job_title,
                    company=company,
                    content=content,
                    word_count=word_count,
                    model_used=self._model,
                )

        except httpx.ConnectError:
            _log.warning("ollama_offline", service="cover_letter")
            return CoverLetterResult(
                job_title=job_title,
                company=company,
                content="",
                word_count=0,
                model_used=self._model,
                error=(
                    "Ollama not running. "
                    "Start with `ollama serve` to use AI cover letter generation."
                ),
            )
        except Exception as exc:
            _log.error("cover_letter_error", exc=str(exc))
            return CoverLetterResult(
                job_title=job_title,
                company=company,
                content="",
                word_count=0,
                model_used=self._model,
                error=str(exc),
            )

    def improve(
        self,
        existing_letter: str,
        feedback: str,
        job_title: str = "",
        company: str = "",
    ) -> CoverLetterResult:
        """Improve an existing cover letter based on feedback."""
        prompt = (
            f"Improve this cover letter based on the following feedback.\n\n"
            f"**Feedback:** {feedback}\n\n"
            f"**Existing Cover Letter:**\n{existing_letter}\n\n"
            f"Return only the improved cover letter body."
        )

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional cover letter editor. "
                        "Return only the improved letter body."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": 600},
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(self._url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = str(data.get("message", {}).get("content", "")).strip()
                word_count = len(re.findall(r"\w+", content))
                return CoverLetterResult(
                    job_title=job_title,
                    company=company,
                    content=content,
                    word_count=word_count,
                    model_used=self._model,
                )
        except httpx.ConnectError:
            return CoverLetterResult(
                job_title=job_title,
                company=company,
                content="",
                word_count=0,
                model_used=self._model,
                error="Ollama not running.",
            )
        except Exception as exc:
            return CoverLetterResult(
                job_title=job_title,
                company=company,
                content="",
                word_count=0,
                model_used=self._model,
                error=str(exc),
            )
