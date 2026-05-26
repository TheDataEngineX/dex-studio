"""Story bank models for Interview Story Bank."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class StoryCategory(StrEnum):
    """Categories for STAR stories."""

    LEADERSHIP = "leadership"
    CHALLENGE = "challenge"
    COLLABORATION = "collaboration"
    IMPACT = "impact"
    FAILURE = "failure"
    GROWTH = "growth"
    PROBLEM_SOLVING = "problem_solving"
    INNOVATION = "innovation"


class Story(BaseModel):
    """A STAR+Reflection story for interview prep."""

    id: str = Field(default_factory=lambda: f"story_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    title: str
    situation: str = Field(description="STAR: Situation context")
    task: str = Field(description="STAR: Task/goal")
    action: str = Field(description="STAR: What you did")
    result: str = Field(description="STAR: Quantifiable outcome")
    reflection: str = Field(description="What you learned and would do differently")
    category: StoryCategory
    tags: list[str] = Field(default_factory=list)
    used_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class StoryBank:
    """In-memory story bank for quick access."""

    def __init__(self) -> None:
        self._stories: list[Story] = []

    def add(self, story: Story) -> None:
        self._stories.append(story)

    def get_all(self) -> list[Story]:
        return sorted(self._stories, key=lambda s: s.updated_at, reverse=True)

    def get_by_category(self, category: StoryCategory) -> list[Story]:
        return [s for s in self._stories if s.category == category]

    def search(self, query: str) -> list[Story]:
        q = query.lower()
        return [
            s
            for s in self._stories
            if q in s.title.lower()
            or q in s.situation.lower()
            or q in s.action.lower()
            or q in q in s.result.lower()
        ]

    def increment_usage(self, story_id: str) -> None:
        for s in self._stories:
            if s.id == story_id:
                s.used_count += 1
                s.updated_at = datetime.now()
                break

    def count(self) -> int:
        return len(self._stories)
