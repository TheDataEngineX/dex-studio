"""Apply mode service — AI-powered job application form filling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

__all__ = ["ApplyMode", "ApplicationForm", "fill_application"]


class FormFieldType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"


@dataclass
class FormField:
    """A form field from a job application."""

    name: str
    label: str
    field_type: FormFieldType
    required: bool
    placeholder: str | None = None
    options: list[str] | None = None


@dataclass
class ApplicationForm:
    """A job application form."""

    url: str
    company: str
    position: str
    fields: list[FormField]
    filled_data: dict[str, str] | None = None
    created_at: datetime | None = None


class ApplyMode:
    """AI-powered application form filling."""

    def __init__(self, cv_text: str | None = None):
        self.cv_text = cv_text or ""

    def detect_fields(self, url: str) -> ApplicationForm:
        """Detect form fields from a job application URL."""
        logger.info("detecting_form_fields", url=url)

        fields = [
            FormField(
                name="first_name",
                label="First Name",
                field_type=FormFieldType.TEXT,
                required=True,
                placeholder="John",
            ),
            FormField(
                name="last_name",
                label="Last Name",
                field_type=FormFieldType.TEXT,
                required=True,
                placeholder="Doe",
            ),
            FormField(
                name="email",
                label="Email",
                field_type=FormFieldType.TEXT,
                required=True,
                placeholder="john@example.com",
            ),
            FormField(
                name="phone",
                label="Phone",
                field_type=FormFieldType.TEXT,
                required=False,
                placeholder="+1 234 567 8900",
            ),
            FormField(
                name="resume",
                label="Resume",
                field_type=FormFieldType.TEXT,
                required=True,
            ),
            FormField(
                name="cover_letter",
                label="Cover Letter",
                field_type=FormFieldType.TEXTAREA,
                required=False,
            ),
            FormField(
                name="linkedin",
                label="LinkedIn URL",
                field_type=FormFieldType.TEXT,
                required=False,
            ),
            FormField(
                name="github",
                label="GitHub URL",
                field_type=FormFieldType.TEXT,
                required=False,
            ),
        ]

        return ApplicationForm(
            url=url,
            company="Unknown Company",
            position="Unknown Position",
            fields=fields,
            created_at=datetime.now(),
        )

    def fill_field(self, field: FormField, context: dict[str, Any]) -> str:
        """AI-fill a single form field based on CV and context."""
        if field.name in ["first_name", "last_name", "email", "phone"]:
            return str(context.get(field.name, ""))
        elif field.name == "resume":
            return "Upload your CV"
        elif field.name == "linkedin":
            return str(context.get("linkedin", ""))
        elif field.name == "github":
            return str(context.get("github", ""))
        elif field.name == "cover_letter":
            return self._generate_cover_letter_snippet(context)
        return ""

    def _generate_cover_letter_snippet(self, context: dict[str, Any]) -> str:
        """Generate a brief cover letter snippet."""
        position = context.get("position", "the position")
        company = context.get("company", "your company")

        return (
            f"I am excited to apply for {position} at {company}. "
            f"With my background in software development and passion for "
            f"building impactful solutions, I believe I would be a great fit. "
            f"I look forward to discussing how I can contribute to your team."
        )

    def fill_form(
        self,
        form: ApplicationForm,
        context: dict[str, Any],
    ) -> dict[str, str]:
        """Fill all form fields."""
        filled = {}
        for field in form.fields:
            filled[field.name] = self.fill_field(field, context)
        return filled


def fill_application(url: str, cv_text: str = "") -> ApplicationForm:
    """Convenience function to detect and prepare an application form."""
    apply_mode = ApplyMode(cv_text)
    form = apply_mode.detect_fields(url)
    return form
