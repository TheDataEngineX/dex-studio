"""Story bank service — manages STAR+Reflection stories for interviews."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import structlog

from careerdex.models.story import Story, StoryBank, StoryCategory

logger = structlog.get_logger()

__all__ = ["StoryBankService", "get_story_bank"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "stories.duckdb"


class StoryBankService:
    """DuckDB-backed story bank service."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        import duckdb

        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stories (
                id VARCHAR PRIMARY KEY,
                title VARCHAR NOT NULL,
                situation TEXT,
                task TEXT,
                action TEXT,
                result TEXT,
                reflection TEXT,
                category VARCHAR NOT NULL,
                tags_json VARCHAR DEFAULT '[]',
                used_count INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        self._memory_bank = StoryBank()
        self._load_all()
        logger.info("story_bank_ready", db=str(self._db_path), count=self._memory_bank.count())

    def _load_all(self) -> None:
        rows = self._conn.execute("SELECT * FROM stories ORDER BY updated_at DESC").fetchall()
        for row in rows:
            story = Story(
                id=str(row[0]),
                title=str(row[1]),
                situation=str(row[2] or ""),
                task=str(row[3] or ""),
                action=str(row[4] or ""),
                result=str(row[5] or ""),
                reflection=str(row[6] or ""),
                category=StoryCategory(str(row[7])),
                tags=json.loads(str(row[8] or "[]")),
                used_count=int(row[9] or 0),
                created_at=datetime.fromisoformat(str(row[10])),
                updated_at=datetime.fromisoformat(str(row[11])),
            )
            self._memory_bank.add(story)

    def add(self, story: Story) -> Story:
        self._conn.execute(
            """
            INSERT INTO stories (
                id, title, situation, task, action, result, reflection,
                category, tags_json, used_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                story.id,
                story.title,
                story.situation,
                story.task,
                story.action,
                story.result,
                story.reflection,
                story.category.value,
                json.dumps(story.tags),
                story.used_count,
                story.created_at.isoformat(),
                story.updated_at.isoformat(),
            ],
        )
        self._memory_bank.add(story)
        logger.info("story_added", id=story.id, title=story.title)
        return story

    def list_all(self) -> list[Story]:
        return self._memory_bank.get_all()

    def list_by_category(self, category: StoryCategory) -> list[Story]:
        return self._memory_bank.get_by_category(category)

    def search(self, query: str) -> list[Story]:
        return self._memory_bank.search(query)

    def increment_usage(self, story_id: str) -> None:
        self._memory_bank.increment_usage(story_id)
        self._conn.execute(
            "UPDATE stories SET used_count = used_count + 1, updated_at = ? WHERE id = ?",
            [datetime.now().isoformat(), story_id],
        )

    def delete(self, story_id: str) -> bool:
        self._conn.execute("DELETE FROM stories WHERE id = ?", [story_id])
        initial_count = self._memory_bank.count()
        self._memory_bank = StoryBank()
        self._load_all()
        return self._memory_bank.count() < initial_count

    def get_recommended_stories(self, count: int = 5) -> list[Story]:
        all_stories = self._memory_bank.get_all()
        return sorted(all_stories, key=lambda s: s.used_count)[:count]

    def close(self) -> None:
        if self._conn:
            self._conn.close()


_story_bank_instance: StoryBankService | None = None


def get_story_bank() -> StoryBankService:
    global _story_bank_instance
    if _story_bank_instance is None:
        _story_bank_instance = StoryBankService()
    return _story_bank_instance
