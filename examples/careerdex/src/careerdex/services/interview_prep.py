"""Interview prep service — loads question bank and scores answers via Ollama.

Questions stored in YAML files under careerdex/data/questions/.
Ollama scoring is fire-and-forget; the page can work without it.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()

__all__ = ["Question", "InterviewPrepService"]

_QUESTIONS_DIR = Path(__file__).parent.parent / "data" / "questions"

# Ollama endpoint (local)
_OLLAMA_URL = "http://localhost:11434/api/generate"
_OLLAMA_MODEL = "llama3.2"

_SCORE_PROMPT = """\
You are a senior engineering interviewer. Evaluate this interview answer and return a JSON object.

Question: {question}

Candidate's answer: {answer}

Return exactly this JSON (no markdown, no explanation):
{{
  "score": <integer 1-10>,
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>"],
  "missing_points": ["<key point not covered>"],
  "verdict": "<one sentence summary>"
}}
"""


class Question:
    """A single interview question with metadata."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data.get("id", "")
        self.question: str = data.get("question", "")
        self.category: str = data.get("category", "")
        self.difficulty: str = data.get("difficulty", "medium")
        self.tags: list[str] = data.get("tags", [])
        self.hints: list[str] = data.get("hints", [])
        self.sample_answer: str = data.get("sample_answer", "")
        self.star_components: dict[str, str] = data.get("star_components", {})
        self.type: str = "behavioral" if self.star_components else "technical"


class InterviewPrepService:
    """Load, filter, and score interview questions.

    Usage::

        svc = InterviewPrepService()
        questions = svc.filter(category="SQL", difficulty="medium")
        feedback = svc.score(question, answer)   # requires Ollama
    """

    def __init__(self) -> None:
        self._questions: list[Question] = []
        self._load_all()

    def _load_all(self) -> None:
        for yaml_file in sorted(_QUESTIONS_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                for q in data.get("questions", []):
                    self._questions.append(Question(q))
                q_count = len(data.get("questions", []))
                logger.info("questions_loaded", file=yaml_file.name, count=q_count)
            except Exception as exc:
                logger.warning("questions_load_failed", file=str(yaml_file), error=str(exc))

    @property
    def all_questions(self) -> list[Question]:
        return list(self._questions)

    @property
    def categories(self) -> list[str]:
        seen: dict[str, None] = {}
        for q in self._questions:
            seen[q.category] = None
        return list(seen)

    def filter(
        self,
        *,
        qtype: str = "",  # "technical" | "behavioral" | ""
        category: str = "",
        difficulty: str = "",
        tag: str = "",
    ) -> list[Question]:
        out = self._questions
        if qtype:
            out = [q for q in out if q.type == qtype]
        if category:
            out = [q for q in out if q.category.lower() == category.lower()]
        if difficulty:
            out = [q for q in out if q.difficulty == difficulty]
        if tag:
            out = [q for q in out if tag.lower() in [t.lower() for t in q.tags]]
        return out

    def random_question(
        self,
        *,
        qtype: str = "",
        difficulty: str = "",
    ) -> Question | None:
        pool = self.filter(qtype=qtype, difficulty=difficulty)
        return random.choice(pool) if pool else None

    def score(self, question: Question, answer: str) -> dict[str, Any]:
        """Score an answer using Ollama. Returns structured feedback dict.

        Raises ConnectionError if Ollama is not running.
        Falls back to a minimal response on JSON parse failure.
        """
        import httpx

        prompt = _SCORE_PROMPT.format(
            question=question.question,
            answer=answer.strip() or "(no answer provided)",
        )

        try:
            resp = httpx.post(
                _OLLAMA_URL,
                json={"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            resp.raise_for_status()
            raw_text: str = resp.json().get("response", "")
            # Strip potential markdown fences
            raw_text = re.sub(r"```(?:json)?", "", raw_text).strip()
            return json.loads(raw_text)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("ollama_score_failed", error=str(exc))
            raise
