"""Tests for JobPosting model — including new extended fields."""

from __future__ import annotations

from careerdex.models.job import JobPosting, JobSource


class TestJobPostingNewFields:
    """Tests for the new fields added in Task 1."""

    def test_is_active_default_true(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.is_active is True

    def test_description_embedding_empty_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.description_embedding == []

    def test_requirements_empty_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.requirements == []

    def test_benefits_empty_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.benefits == []

    def test_metadata_empty_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.metadata == {}

    def test_last_synced_at_set_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.last_synced_at is not None

    def test_company_id_empty_by_default(self) -> None:
        job = JobPosting(title="Engineer", company="Acme")
        assert job.company_id == ""


class TestJobPostingSerialization:
    """Test serialization/deserialization with all new fields."""

    def test_serialization_with_all_new_fields(self) -> None:
        job = JobPosting(
            title="Senior Engineer",
            company="Google",
            company_id="google",
            description_embedding=[0.1] * 384,
            requirements=["Python", "SQL"],
            benefits=["401k", "Remote"],
            is_active=True,
            metadata={"source_job_id": "12345"},
        )
        data = job.model_dump()
        assert data["company_id"] == "google"
        assert len(data["description_embedding"]) == 384
        assert data["requirements"] == ["Python", "SQL"]
        assert data["benefits"] == ["401k", "Remote"]
        assert data["is_active"] is True
        assert data["metadata"]["source_job_id"] == "12345"

    def test_deserialization_with_all_new_fields(self) -> None:
        data = {
            "title": "Staff Engineer",
            "company": "Meta",
            "company_id": "meta",
            "description_embedding": [0.5] * 384,
            "requirements": ["React", "TypeScript"],
            "benefits": ["Stock", "Food"],
            "is_active": False,
            "metadata": {"external_id": "abc"},
        }
        job = JobPosting(**data)
        assert job.company_id == "meta"
        assert job.description_embedding == [0.5] * 384
        assert job.requirements == ["React", "TypeScript"]
        assert job.is_active is False


class TestCompanyIdNormalization:
    """Test company_id normalization."""

    def test_company_id_matches_company_slug(self) -> None:
        job = JobPosting(
            title="Engineer",
            company="Alphabet Inc.",
            company_id="alphabet",
        )
        assert job.company_id == "alphabet"

    def test_company_id_empty_when_not_provided(self) -> None:
        job = JobPosting(title="Engineer", company="Unknown Co.")
        assert job.company_id == ""


class TestJobSourceLinkedIn:
    """Test LINKEDIN enum value."""

    def test_linkedin_is_valid_source(self) -> None:
        assert JobSource.LINKEDIN == "linkedin"

    def test_job_posting_accepts_linkedin_source(self) -> None:
        job = JobPosting(
            title="Engineer",
            company="Acme",
            source=JobSource.LINKEDIN,
        )
        assert job.source == JobSource.LINKEDIN

    def test_job_posting_serialization_with_linkedin(self) -> None:
        job = JobPosting(
            title="Engineer",
            company="Acme",
            source=JobSource.LINKEDIN,
        )
        data = job.model_dump()
        assert data["source"] == "linkedin"

    def test_job_posting_deserialization_from_linkedin(self) -> None:
        data = {
            "title": "Engineer",
            "company": "Acme",
            "source": "linkedin",
        }
        job = JobPosting(**data)
        assert job.source == JobSource.LINKEDIN
