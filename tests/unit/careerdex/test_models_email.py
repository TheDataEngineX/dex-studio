"""Unit tests for careerdex email models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from careerdex.models.email import (
    EmailCategory,
    EmailConfig,
    EmailMatchResult,
    EmailMessage,
)


class TestEmailCategory:
    def test_required_values_exist(self) -> None:
        assert EmailCategory.APPLICATION_CONFIRMATION == "application_confirmation"
        assert EmailCategory.REJECTION == "rejection"
        assert EmailCategory.OFFER == "offer"
        assert EmailCategory.UNKNOWN == "unknown"

    def test_all_categories(self) -> None:
        names = {e.value for e in EmailCategory}
        assert "recruiter_outreach" in names
        assert "interview_invite" in names
        assert "follow_up" in names
        assert "status_update" in names
        assert "networking" in names

    def test_is_str_enum(self) -> None:
        assert str(EmailCategory.UNKNOWN) == "unknown"


class TestEmailConfig:
    def test_defaults(self) -> None:
        cfg = EmailConfig()
        assert cfg.host == "imap.gmail.com"
        assert cfg.port == 993
        assert cfg.use_ssl is True
        assert cfg.max_fetch == 50
        assert cfg.days_back == 7
        assert cfg.username == ""
        assert cfg.password == ""

    def test_default_folders(self) -> None:
        cfg = EmailConfig()
        assert cfg.folders == ["INBOX"]

    def test_custom_config(self) -> None:
        cfg = EmailConfig(
            host="outlook.office365.com",
            port=993,
            username="user@example.com",
            password="secret",
            max_fetch=100,
            days_back=14,
        )
        assert cfg.host == "outlook.office365.com"
        assert cfg.max_fetch == 100
        assert cfg.days_back == 14

    def test_folders_independent(self) -> None:
        cfg1 = EmailConfig()
        cfg2 = EmailConfig()
        cfg1.folders.append("Sent")
        assert cfg2.folders == ["INBOX"]


class TestEmailMessage:
    def test_id_generated(self) -> None:
        m1 = EmailMessage()
        m2 = EmailMessage()
        assert m1.id != m2.id
        assert len(m1.id) == 16

    def test_category_default_unknown(self) -> None:
        m = EmailMessage()
        assert m.category == EmailCategory.UNKNOWN

    def test_date_default_set(self) -> None:
        before = datetime.now(UTC)
        m = EmailMessage()
        after = datetime.now(UTC)
        assert before <= m.date <= after

    def test_defaults(self) -> None:
        m = EmailMessage()
        assert m.subject == ""
        assert m.sender == ""
        assert m.sender_name == ""
        assert m.recipients == []
        assert m.body_text == ""
        assert m.body_html == ""
        assert m.folder == "INBOX"
        assert m.is_read is False
        assert m.extracted_company == ""
        assert m.extracted_position == ""
        assert m.keywords_found == []

    def test_full_construction(self) -> None:
        now = datetime.now(UTC)
        m = EmailMessage(
            subject="Application Received",
            sender="noreply@acme.com",
            sender_name="Acme Recruiting",
            recipients=["candidate@example.com"],
            date=now,
            body_text="Thank you for applying.",
            folder="INBOX",
            is_read=True,
            category=EmailCategory.APPLICATION_CONFIRMATION,
            extracted_company="Acme",
            extracted_position="Data Engineer",
            keywords_found=["application", "received"],
        )
        assert m.subject == "Application Received"
        assert m.category == EmailCategory.APPLICATION_CONFIRMATION
        assert m.extracted_company == "Acme"
        assert m.is_read is True
        assert m.date == now


class TestEmailMatchResult:
    def test_construction(self) -> None:
        result = EmailMatchResult(
            email_id="abc123",
            application_id="xyz789",
            confidence=0.85,
            match_reason="company name match",
        )
        assert result.email_id == "abc123"
        assert result.application_id == "xyz789"
        assert result.confidence == pytest.approx(0.85)
        assert result.match_reason == "company name match"

    def test_confidence_range(self) -> None:
        r = EmailMatchResult(
            email_id="a",
            application_id="b",
            confidence=1.0,
            match_reason="exact",
        )
        assert 0.0 <= r.confidence <= 1.0
