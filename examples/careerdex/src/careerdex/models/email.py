"""Email integration models — IMAP config and parsed messages."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "EmailConfig",
    "EmailMessage",
    "EmailMatchResult",
    "EmailCategory",
]


class EmailCategory(StrEnum):
    """Categorisation of a job-related email."""

    APPLICATION_CONFIRMATION = "application_confirmation"
    RECRUITER_OUTREACH = "recruiter_outreach"
    INTERVIEW_INVITE = "interview_invite"
    REJECTION = "rejection"
    OFFER = "offer"
    FOLLOW_UP = "follow_up"
    STATUS_UPDATE = "status_update"
    NETWORKING = "networking"
    UNKNOWN = "unknown"


class EmailConfig(BaseModel):
    """IMAP connection settings.

    Works with Gmail (imap.gmail.com:993, App Password),
    Outlook (outlook.office365.com:993), or any IMAP server.
    """

    host: str = "imap.gmail.com"
    port: int = 993
    username: str = ""
    password: str = ""  # App Password for Gmail, regular password for others
    use_ssl: bool = True
    folders: list[str] = Field(default_factory=lambda: ["INBOX"])
    max_fetch: int = 50  # max emails to fetch per scan
    days_back: int = 7  # how far back to scan


class EmailMessage(BaseModel):
    """A parsed email message."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    message_id: str = ""  # RFC 2822 Message-ID
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    recipients: list[str] = Field(default_factory=list)
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    body_text: str = ""
    body_html: str = ""
    folder: str = "INBOX"
    is_read: bool = False
    category: EmailCategory = EmailCategory.UNKNOWN
    extracted_company: str = ""
    extracted_position: str = ""
    keywords_found: list[str] = Field(default_factory=list)


class EmailMatchResult(BaseModel):
    """Result of matching an email to a tracked application."""

    email_id: str
    application_id: str
    confidence: float  # 0.0 to 1.0
    match_reason: str  # e.g. "company name match", "position title match"
