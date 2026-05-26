"""Progress service — DuckDB-backed skill snapshots + Ollama improvement suggestions.

Snapshots stored in ``~/.dex-studio/careerdex/progress.duckdb``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from careerdex.models.progress import (
    SkillDelta,
    SkillRating,
    SkillSnapshot,
)

logger = structlog.get_logger()

__all__ = ["ProgressService"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "progress.duckdb"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS snapshots (
    id           VARCHAR PRIMARY KEY,
    date         TIMESTAMP NOT NULL,
    ratings_json VARCHAR DEFAULT '[]',
    notes        VARCHAR DEFAULT '',
    created_at   TIMESTAMP NOT NULL
);
"""

_OLLAMA_URL = "http://localhost:11434/api/generate"
_OLLAMA_MODEL = "llama3.2"

_IMPROVEMENT_PROMPT = """\
You are a senior data engineering career coach.
Analyse this skill assessment and give targeted advice.

Current skills (name: rating/10):
{current_skills}

{delta_section}
Focus on the weakest skills and the biggest drops.
Return exactly this JSON (no markdown):
{{
  "focus_areas": [
    {{"skill": "<name>", "priority": "high|medium", "action": "<action this week>"}}
  ],
  "strengths_to_leverage": ["<strength 1>", "<strength 2>"],
  "weekly_goal": "<one concrete goal for the next 7 days>",
  "resources": [{{"skill": "<skill>", "resource": "<book/course/project name>"}}]
}}
"""


class ProgressService:
    """DuckDB-backed skill snapshot storage and delta computation.

    Usage::

        svc = ProgressService()
        snap = svc.add_snapshot(SkillSnapshot(ratings=[...]))
        deltas = svc.compute_delta()          # latest vs previous
        plan = svc.suggest_improvements()     # Ollama advice
        svc.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(_CREATE_TABLE)

    def close(self) -> None:
        self._conn.close()

    # -- Snapshots -----------------------------------------------------------

    def add_snapshot(self, snapshot: SkillSnapshot) -> SkillSnapshot:
        self._conn.execute(
            """
            INSERT INTO snapshots (id, date, ratings_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                snapshot.id,
                snapshot.date.isoformat(),
                json.dumps([r.model_dump(mode="json") for r in snapshot.ratings]),
                snapshot.notes,
                snapshot.created_at.isoformat(),
            ],
        )
        logger.info("snapshot_added", id=snapshot.id, skills=snapshot.skill_count)
        return snapshot

    def list_snapshots(self) -> list[SkillSnapshot]:
        """Return all snapshots, newest first."""
        rows = self._conn.execute("SELECT * FROM snapshots ORDER BY date DESC").fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def get_latest(self) -> SkillSnapshot | None:
        row = self._conn.execute("SELECT * FROM snapshots ORDER BY date DESC LIMIT 1").fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_previous(self) -> SkillSnapshot | None:
        """Return the second-most-recent snapshot."""
        row = self._conn.execute(
            "SELECT * FROM snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def delete_snapshot(self, snapshot_id: str) -> bool:
        existing = self._conn.execute(
            "SELECT id FROM snapshots WHERE id = ?", [snapshot_id]
        ).fetchone()
        if existing is None:
            return False
        self._conn.execute("DELETE FROM snapshots WHERE id = ?", [snapshot_id])
        logger.info("snapshot_deleted", id=snapshot_id)
        return True

    def total(self) -> int:
        result = self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()
        return result[0] if result else 0

    # -- Delta ---------------------------------------------------------------

    def compute_delta(
        self,
        current: SkillSnapshot | None = None,
        previous: SkillSnapshot | None = None,
    ) -> list[SkillDelta]:
        """Compute per-skill deltas between two snapshots.

        Defaults to the two most recent snapshots.
        Returns empty list if fewer than two snapshots exist.
        """
        cur = current or self.get_latest()
        prev = previous or self.get_previous()
        if cur is None or prev is None:
            return []

        prev_map: dict[str, SkillRating] = {r.skill.lower(): r for r in prev.ratings}
        deltas: list[SkillDelta] = []

        for rating in cur.ratings:
            key = rating.skill.lower()
            if key in prev_map:
                deltas.append(
                    SkillDelta.compute(
                        skill=rating.skill,
                        category=rating.category,
                        previous=prev_map[key].rating,
                        current=rating.rating,
                    )
                )

        return sorted(deltas, key=lambda d: abs(d.delta), reverse=True)

    # -- Ollama suggestions --------------------------------------------------

    def suggest_improvements(
        self,
        snapshot: SkillSnapshot | None = None,
        deltas: list[SkillDelta] | None = None,
    ) -> dict[str, Any]:
        """Generate an improvement plan via local Ollama.

        Raises RuntimeError if Ollama is unreachable.
        """
        import httpx

        cur = snapshot or self.get_latest()
        if cur is None:
            raise RuntimeError("No snapshot available — complete an assessment first.")

        dl = deltas if deltas is not None else self.compute_delta()

        skill_lines = "\n".join(
            f"  {r.skill} ({r.category.value.replace('_', ' ')}): {r.rating}/10"
            for r in sorted(cur.ratings, key=lambda r: r.rating)
        )

        if dl:

            def _sign(x: int) -> str:
                return "+" if x >= 0 else ""

            delta_lines = "Changes since last assessment:\n" + "\n".join(
                f"  {d.skill}: {d.previous_rating} → {d.current_rating} ({_sign(d.delta)}{d.delta})"
                for d in dl[:10]
            )
        else:
            delta_lines = "No previous assessment to compare against."

        prompt = _IMPROVEMENT_PROMPT.format(
            current_skills=skill_lines,
            delta_section=delta_lines,
        )

        try:
            resp = httpx.post(
                _OLLAMA_URL,
                json={"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=90.0,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            result: dict[str, Any] = json.loads(raw)
            logger.info("improvement_plan_generated")
            return result
        except Exception as exc:
            logger.warning("improvement_plan_failed", error=str(exc))
            raise RuntimeError(f"Ollama unavailable: {exc}") from exc

    # -- private -------------------------------------------------------------

    def _row_to_snapshot(self, row: tuple[object, ...]) -> SkillSnapshot:
        id_, date, ratings_json, notes, created_at = row

        ratings: list[SkillRating] = []
        try:
            for d in json.loads(str(ratings_json or "[]")):
                ratings.append(SkillRating(**d))
        except (json.JSONDecodeError, TypeError):
            pass

        return SkillSnapshot(
            id=str(id_),
            date=_parse_dt(date) or datetime.now(UTC),
            ratings=ratings,
            notes=str(notes or ""),
            created_at=_parse_dt(created_at) or datetime.now(UTC),
        )


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None
