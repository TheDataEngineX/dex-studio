"""Networking models — contacts, interactions, and outreach tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "ContactRelationship",
    "InteractionType",
    "Interaction",
    "NetworkContact",
]


class ContactRelationship(StrEnum):
    """How this contact relates to the job search."""

    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    PEER = "peer"
    MENTOR = "mentor"
    REFERRAL = "referral"
    COWORKER = "coworker"
    ALUMNI = "alumni"
    OTHER = "other"


class InteractionType(StrEnum):
    """Type of interaction logged with a contact."""

    EMAIL = "email"
    LINKEDIN = "linkedin"
    CALL = "call"
    MEETING = "meeting"
    COFFEE_CHAT = "coffee_chat"
    REFERRAL_REQUESTED = "referral_requested"
    REFERRAL_GIVEN = "referral_given"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class Interaction(BaseModel):
    """A single logged interaction with a contact."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: InteractionType = InteractionType.EMAIL
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = ""
    outcome: str = ""  # e.g. "scheduled call", "no response", "referral pending"


class NetworkContact(BaseModel):
    """A person in the professional network."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    title: str = ""
    company: str = ""
    email: str = ""
    linkedin_url: str = ""
    relationship: ContactRelationship = ContactRelationship.OTHER
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    interactions: list[Interaction] = Field(default_factory=list)
    next_follow_up: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Application this contact is linked to (optional)
    application_id: str = ""

    @property
    def last_contact(self) -> datetime | None:
        """Date of most recent interaction."""
        if not self.interactions:
            return None
        return max(i.date for i in self.interactions)

    @property
    def interaction_count(self) -> int:
        return len(self.interactions)
