"""Resume domain model.

Designed for IT/data-engineering roles: explicit sections for skills,
certifications, projects, and publications alongside the standard experience
and education blocks.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "ContactInfo",
    "WorkExperience",
    "Education",
    "Certification",
    "Project",
    "Publication",
    "SkillGroup",
    "Resume",
]


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    title: str = ""  # current/desired title shown under name


class WorkExperience(BaseModel):
    company: str
    title: str
    location: str = ""
    start_date: str = ""  # free-form: "Jan 2022", "2022", etc.
    end_date: str = ""  # empty = "Present"
    current: bool = False
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str
    field: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""
    honors: list[str] = Field(default_factory=list)
    relevant_coursework: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str
    issuer: str = ""
    date_earned: str = ""
    expiry: str = ""
    credential_id: str = ""
    url: str = ""


class Project(BaseModel):
    name: str
    description: str = ""
    role: str = ""
    url: str = ""
    repo: str = ""
    technologies: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""


class Publication(BaseModel):
    title: str
    venue: str = ""  # journal, conference, blog
    date: str = ""
    url: str = ""
    authors: list[str] = Field(default_factory=list)


class SkillGroup(BaseModel):
    """Named group of skills for the skills section."""

    category: str  # e.g. "Languages", "Cloud", "Tools"
    skills: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    """Full resume document."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: str = ""
    skills: list[SkillGroup] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)

    # Layout control
    template: Literal["classic", "compact", "modern"] = "classic"
    accent_color: str = "#6366f1"  # hex color used in template headings
    font_size_pt: int = 10  # body font size in points

    # Metadata
    target_role: str = ""
    version_label: str = ""
    last_updated: date | None = None
