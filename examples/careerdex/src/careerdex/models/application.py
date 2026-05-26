"""Application tracking models — state machine for job applications."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "ApplicationStatus",
    "ApplicationEntry",
    "ApplicationNote",
    "ApplicationEvent",
    "STATUS_TRANSITIONS",
]


class ApplicationStatus(StrEnum):
    """Job application lifecycle states."""

    SAVED = "saved"
    APPLIED = "applied"
    REACHED_OUT = "reached_out"
    RESPONDED = "responded"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    TECHNICAL = "technical"
    FINAL_ROUND = "final_round"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"


# Valid state transitions — prevents invalid status jumps
STATUS_TRANSITIONS: dict[ApplicationStatus, list[ApplicationStatus]] = {
    ApplicationStatus.SAVED: [
        ApplicationStatus.APPLIED,
        ApplicationStatus.REACHED_OUT,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.APPLIED: [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.PHONE_SCREEN,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.GHOSTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.REACHED_OUT: [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.APPLIED,
        ApplicationStatus.GHOSTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.RESPONDED: [
        ApplicationStatus.PHONE_SCREEN,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.PHONE_SCREEN: [
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.TECHNICAL,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.INTERVIEW: [
        ApplicationStatus.TECHNICAL,
        ApplicationStatus.FINAL_ROUND,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.TECHNICAL: [
        ApplicationStatus.FINAL_ROUND,
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.FINAL_ROUND: [
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.OFFER: [
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.ACCEPTED: [],
    ApplicationStatus.REJECTED: [],
    ApplicationStatus.WITHDRAWN: [],
    ApplicationStatus.GHOSTED: [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.WITHDRAWN,
    ],
}


class ApplicationNote(BaseModel):
    """A timestamped note on an application."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApplicationEvent(BaseModel):
    """Status change event for audit trail."""

    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""


class ApplicationEntry(BaseModel):
    """A tracked job application."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    company: str
    position: str
    url: str = ""
    location: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "USD"
    status: ApplicationStatus = ApplicationStatus.SAVED
    source: str = ""  # where the job was found (linkedin, indeed, referral, etc.)
    contact_name: str = ""
    contact_email: str = ""
    notes: list[ApplicationNote] = Field(default_factory=list)
    events: list[ApplicationEvent] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None
    next_follow_up: datetime | None = None

    def can_transition(self, new_status: ApplicationStatus) -> bool:
        """Check if a status transition is valid."""
        return new_status in STATUS_TRANSITIONS.get(self.status, [])

    def transition(self, new_status: ApplicationStatus, reason: str = "") -> None:
        """Move to a new status, recording the event."""
        if not self.can_transition(new_status):
            msg = f"Cannot move from {self.status} to {new_status}"
            raise ValueError(msg)
        self.events.append(
            ApplicationEvent(
                from_status=self.status,
                to_status=new_status,
                reason=reason,
            )
        )
        self.status = new_status
        self.updated_at = datetime.now(UTC)
        if new_status == ApplicationStatus.APPLIED and self.applied_at is None:
            self.applied_at = self.updated_at
