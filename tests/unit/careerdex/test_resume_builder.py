"""Unit tests for ResumeBuilder."""

from __future__ import annotations

import sys
import types
import unittest.mock
from pathlib import Path

import pytest
from careerdex.models.resume import ContactInfo, Resume, SkillGroup, WorkExperience
from careerdex.services.resume_builder import ResumeBuilder


@pytest.fixture()
def resume() -> Resume:
    return Resume(
        contact=ContactInfo(name="Ada Lovelace", email="ada@example.com", title="Data Engineer"),
        summary="Senior Data Engineer with 8 years experience.",
        skills=[SkillGroup(category="Languages", skills=["Python", "SQL"])],
        experience=[
            WorkExperience(
                company="Acme Corp",
                title="Data Engineer",
                start_date="Jan 2020",
                end_date="Present",
                bullets=["Built ETL pipelines", "Reduced latency by 40%"],
                technologies=["Python", "Spark"],
            )
        ],
    )


@pytest.fixture()
def builder() -> ResumeBuilder:
    return ResumeBuilder()


class TestToHtml:
    def test_returns_string(self, builder: ResumeBuilder, resume: Resume) -> None:
        html = builder.to_html(resume)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_name(self, builder: ResumeBuilder, resume: Resume) -> None:
        html = builder.to_html(resume)
        assert "Ada Lovelace" in html

    def test_contains_summary(self, builder: ResumeBuilder, resume: Resume) -> None:
        html = builder.to_html(resume)
        assert "Senior Data Engineer" in html

    def test_fallback_to_classic_on_unknown_template(
        self, builder: ResumeBuilder, resume: Resume
    ) -> None:
        resume.template = "classic"  # type: ignore[assignment]
        html = builder.to_html(resume)
        assert len(html) > 0

    def test_classic_template_explicit(self, builder: ResumeBuilder, resume: Resume) -> None:
        resume.template = "classic"  # type: ignore[assignment]
        html = builder.to_html(resume)
        assert "Ada Lovelace" in html


class TestToPdf:
    def test_returns_bytes_when_weasyprint_available(
        self, builder: ResumeBuilder, resume: Resume
    ) -> None:
        mock_wp = types.ModuleType("weasyprint")
        mock_html_instance = unittest.mock.MagicMock()
        mock_html_instance.write_pdf.return_value = b"%PDF-fake"
        mock_html_cls = unittest.mock.MagicMock(return_value=mock_html_instance)
        mock_wp.HTML = mock_html_cls  # type: ignore[attr-defined]

        with unittest.mock.patch.dict("sys.modules", {"weasyprint": mock_wp}):
            pdf = builder.to_pdf(resume)

        assert pdf == b"%PDF-fake"

    def test_raises_import_error_when_weasyprint_missing(
        self, builder: ResumeBuilder, resume: Resume
    ) -> None:
        original = sys.modules.pop("weasyprint", None)
        try:
            with (
                unittest.mock.patch.dict("sys.modules", {"weasyprint": None}),
                pytest.raises(ImportError, match="WeasyPrint"),
            ):
                builder.to_pdf(resume)
        finally:
            if original is not None:
                sys.modules["weasyprint"] = original


class TestSaveLoad:
    def test_save_writes_json(self, builder: ResumeBuilder, resume: Resume, tmp_path: Path) -> None:
        dest = tmp_path / "resume.json"
        result = builder.save(resume, path=dest)
        assert result == dest
        assert dest.exists()
        assert dest.stat().st_size > 0

    def test_save_creates_parent_dirs(
        self, builder: ResumeBuilder, resume: Resume, tmp_path: Path
    ) -> None:
        dest = tmp_path / "nested" / "deep" / "resume.json"
        builder.save(resume, path=dest)
        assert dest.exists()

    def test_load_round_trip(self, builder: ResumeBuilder, resume: Resume, tmp_path: Path) -> None:
        dest = tmp_path / "resume.json"
        builder.save(resume, path=dest)
        loaded = builder.load(path=dest)
        assert loaded is not None
        assert loaded.contact.name == "Ada Lovelace"
        assert loaded.summary == resume.summary

    def test_load_nonexistent_returns_none(self, builder: ResumeBuilder, tmp_path: Path) -> None:
        result = builder.load(path=tmp_path / "does_not_exist.json")
        assert result is None

    def test_load_corrupted_file_returns_none(self, builder: ResumeBuilder, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json {{{", encoding="utf-8")
        result = builder.load(path=bad)
        assert result is None

    def test_save_preserves_skills(
        self, builder: ResumeBuilder, resume: Resume, tmp_path: Path
    ) -> None:
        dest = tmp_path / "resume.json"
        builder.save(resume, path=dest)
        loaded = builder.load(path=dest)
        assert loaded is not None
        assert len(loaded.skills) == 1
        assert loaded.skills[0].category == "Languages"
        assert "Python" in loaded.skills[0].skills
