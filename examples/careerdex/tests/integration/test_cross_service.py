"""Cross-service integration tests — ResumeMatcher, Tracker, Networking workflows."""

from __future__ import annotations

from pathlib import Path

from careerdex.models.application import ApplicationEntry, ApplicationStatus
from careerdex.models.networking import ContactRelationship, NetworkContact
from careerdex.models.resume import ContactInfo, Resume, SkillGroup, WorkExperience
from careerdex.services.networking import NetworkingService
from careerdex.services.resume_matcher import MatchResult, ResumeMatcher
from careerdex.services.tracker import ApplicationTracker


class TestResumeMatcher:
    def test_match_text_returns_match_result(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Experienced Python developer with SQL and AWS skills",
            job_description="Looking for Python and SQL data engineer with AWS experience",
        )
        assert isinstance(result, MatchResult)
        assert 0 <= result.overall_score <= 100

    def test_match_text_finds_matched_skills(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Expert in Python, SQL, Spark, Kafka, and AWS",
            job_description="Data engineer: Python, SQL, Spark required. Kafka a plus.",
        )
        lower_matched = {s.lower() for s in result.matched_skills}
        assert "python" in lower_matched
        assert "sql" in lower_matched

    def test_match_text_identifies_missing_skills(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="Python developer with no cloud experience",
            job_description="Need Python and Kubernetes and Terraform expert",
        )
        lower_missing = {s.lower() for s in result.missing_skills}
        assert "kubernetes" in lower_missing or "terraform" in lower_missing

    def test_high_overlap_high_score(self) -> None:
        matcher = ResumeMatcher()
        jd = "Python SQL Spark Kafka Airflow dbt data engineering ETL machine learning"
        resume = "Python SQL Spark Kafka Airflow dbt data engineering ETL machine learning"
        result = matcher.match_text(resume_text=resume, job_description=jd)
        assert result.overall_score >= 60

    def test_zero_overlap_low_score(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text(
            resume_text="graphic designer photoshop illustrator",
            job_description="Python SQL Spark data engineering machine learning",
        )
        assert result.overall_score < 50

    def test_match_mode_is_keyword(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text("python sql", "python developer needed")
        assert result.analysis_mode == "keyword"

    def test_match_resume_object(self) -> None:
        matcher = ResumeMatcher()
        resume = Resume(
            contact=ContactInfo(name="Jay M", title="Data Engineer"),
            summary="Python, SQL, Spark, Airflow data engineer with 5 years experience",
            skills=[
                SkillGroup(category="Data", skills=["Python", "SQL", "Spark", "Kafka", "Airflow"])
            ],
            experience=[
                WorkExperience(
                    company="Acme",
                    title="Data Engineer",
                    bullets=["Built Python ETL pipelines", "Managed SQL databases"],
                )
            ],
        )
        result = matcher.match(
            resume,
            "Python and SQL data engineer needed. Spark experience required.",
        )
        assert isinstance(result, MatchResult)
        assert result.overall_score >= 0

    def test_empty_jd_returns_50_score(self) -> None:
        matcher = ResumeMatcher()
        result = matcher.match_text("python sql spark", "")
        assert result.overall_score == 50.0
        assert result.matched_skills == []


class TestTrackerNetworkingCrossService:
    def test_contact_linked_to_application(self, tmp_path: Path) -> None:
        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        net = NetworkingService(db_path=tmp_path / "net.duckdb")

        app = ApplicationEntry(company="DataCorp", position="Data Engineer")
        tracker.add(app)

        contact = NetworkContact(
            name="Alice Recruiter",
            company="DataCorp",
            relationship=ContactRelationship.RECRUITER,
            application_id=app.id,
        )
        net.add(contact)

        retrieved_contact = net.get(contact.id)
        assert retrieved_contact is not None
        assert retrieved_contact.application_id == app.id

        retrieved_app = tracker.get(app.id)
        assert retrieved_app is not None
        assert retrieved_app.company == "DataCorp"

        tracker.close()
        net.close()

    def test_status_progression_with_contact_interaction(self, tmp_path: Path) -> None:
        from careerdex.models.networking import Interaction, InteractionType

        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        net = NetworkingService(db_path=tmp_path / "net.duckdb")

        app = ApplicationEntry(company="TechCo", position="ML Engineer")
        tracker.add(app)
        tracker.update_status(app.id, ApplicationStatus.APPLIED)

        contact = NetworkContact(
            name="Bob Recruiter",
            company="TechCo",
            relationship=ContactRelationship.RECRUITER,
            application_id=app.id,
        )
        net.add(contact)
        net.log_interaction(
            contact.id,
            Interaction(type=InteractionType.EMAIL, note="Reached out about ML position"),
        )

        tracker.update_status(app.id, ApplicationStatus.PHONE_SCREEN)

        final_app = tracker.get(app.id)
        assert final_app is not None
        assert final_app.status == ApplicationStatus.PHONE_SCREEN

        final_contact = net.get(contact.id)
        assert final_contact is not None
        assert final_contact.interaction_count == 1

        tracker.close()
        net.close()

    def test_resume_match_informs_application(self, tmp_path: Path) -> None:
        tracker = ApplicationTracker(db_path=tmp_path / "apps.duckdb")
        matcher = ResumeMatcher()

        jd = "Senior Python data engineer with Spark, SQL, Kafka, and AWS experience required"
        resume_text = "Python developer with SQL databases, Spark, and AWS cloud experience"

        match_result = matcher.match_text(resume_text=resume_text, job_description=jd)

        if match_result.overall_score >= 30:
            app = ApplicationEntry(
                company="DataPipelines Inc",
                position="Senior Data Engineer",
            )
            tracker.add(app)
            tracker.update_status(app.id, ApplicationStatus.APPLIED)
            tracker.add_note(app.id, f"Match score: {match_result.overall_score:.0f}%")

        entries = tracker.list_all(status=ApplicationStatus.APPLIED)
        assert len(entries) >= 1
        assert entries[0].notes[0].text.startswith("Match score:")
        tracker.close()


class TestServiceInit:
    def test_tracker_initializes(self, tmp_path: Path) -> None:
        svc = ApplicationTracker(db_path=tmp_path / "app.duckdb")
        assert svc is not None
        svc.close()

    def test_networking_initializes(self, tmp_path: Path) -> None:
        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        assert svc is not None
        svc.close()

    def test_progress_initializes(self, tmp_path: Path) -> None:
        from careerdex.services.progress import ProgressService

        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        assert svc is not None
        svc.close()

    def test_resume_matcher_initializes(self) -> None:
        assert ResumeMatcher() is not None

    def test_interview_prep_initializes(self) -> None:
        from careerdex.services.interview_prep import InterviewPrepService

        assert InterviewPrepService() is not None

    def test_models_are_serializable(self) -> None:
        entry = ApplicationEntry(company="Test Co", position="Engineer")
        data = entry.model_dump(mode="json")
        assert data["company"] == "Test Co"
        restored = ApplicationEntry(**data)
        assert restored.company == "Test Co"
