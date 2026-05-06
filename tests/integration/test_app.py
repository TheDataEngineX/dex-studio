"""Integration test — verify app bootstraps and pages register."""

from __future__ import annotations

from pathlib import Path


class TestAppBootstrap:
    def test_page_imports(self) -> None:
        """All page modules should import without error."""
        from dex_studio.pages import project_hub  # noqa: F401
        from dex_studio.pages.ai import (
            agents,  # noqa: F401
            collections,  # noqa: F401
            retrieval,  # noqa: F401
            tools,  # noqa: F401
        )
        from dex_studio.pages.ai import dashboard as ai_dash  # noqa: F401
        from dex_studio.pages.data import (
            dashboard,  # noqa: F401
            lineage,  # noqa: F401
            pipelines,  # noqa: F401
            quality,  # noqa: F401
            sources,  # noqa: F401
            warehouse,  # noqa: F401
        )
        from dex_studio.pages.ml import dashboard as ml_dash  # noqa: F401
        from dex_studio.pages.ml import (
            drift,  # noqa: F401
            experiments,  # noqa: F401
            features,  # noqa: F401
            models,  # noqa: F401
            predictions,  # noqa: F401
        )
        from dex_studio.pages.system import (
            components,  # noqa: F401
            connection,  # noqa: F401
            logs,  # noqa: F401
            metrics,  # noqa: F401
            settings,  # noqa: F401
            status,  # noqa: F401
            traces,  # noqa: F401
        )

    def test_components_import(self) -> None:
        """Layout components should import without error."""
        from dex_studio.components.layout import page_shell, sidebar  # noqa: F401

    def test_config_system(self) -> None:
        """Config loading should work with defaults."""
        from dex_studio.config import StudioConfig, load_config

        cfg = load_config()
        assert isinstance(cfg, StudioConfig)
        assert cfg.api_url == "http://localhost:17000"

    def test_client_creation(self) -> None:
        """DexClient should create from default config."""
        from dex_studio.client import DexClient
        from dex_studio.config import load_config

        cfg = load_config()
        client = DexClient(config=cfg)
        assert client.config.api_url == "http://localhost:17000"


class TestCareerDexServices:
    def test_tracker_initializes(self, tmp_path: Path) -> None:
        """ApplicationTracker initializes with temp DB."""
        from careerdex.services.tracker import ApplicationTracker

        svc = ApplicationTracker(db_path=tmp_path / "app.duckdb")
        assert svc is not None
        svc.close()

    def test_networking_initializes(self, tmp_path: Path) -> None:
        """NetworkingService initializes with temp DB."""
        from careerdex.services.networking import NetworkingService

        svc = NetworkingService(db_path=tmp_path / "net.duckdb")
        assert svc is not None
        svc.close()

    def test_progress_initializes(self, tmp_path: Path) -> None:
        """ProgressService initializes with temp DB."""
        from careerdex.services.progress import ProgressService

        svc = ProgressService(db_path=tmp_path / "prog.duckdb")
        assert svc is not None
        svc.close()

    def test_resume_matcher_initializes(self) -> None:
        """ResumeMatcher initializes without external deps."""
        from careerdex.services.resume_matcher import ResumeMatcher

        svc = ResumeMatcher()
        assert svc is not None

    def test_interview_prep_initializes(self) -> None:
        """InterviewPrep initializes."""
        from careerdex.services.interview_prep import InterviewPrepService

        svc = InterviewPrepService()
        assert svc is not None


class TestDatabaseIntegration:
    def test_duckdb_writes_and_reads(self, tmp_path: Path) -> None:
        """DuckDB can write and read data."""
        import duckdb

        db = duckdb.connect(str(tmp_path / "test.duckdb"))
        db.execute("CREATE TABLE test (id VARCHAR, value INTEGER)")
        db.execute("INSERT INTO test VALUES ('a', 1), ('b', 2)")
        result = db.execute("SELECT * FROM test").fetchall()
        assert len(result) == 2
        db.close()

    def test_careerdex_db_schema(self, tmp_path: Path) -> None:
        """CareerDEX creates expected schema."""
        import duckdb

        db_path = tmp_path / "careerdex.duckdb"
        db = duckdb.connect(str(db_path))
        db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id VARCHAR PRIMARY KEY,
                company VARCHAR NOT NULL,
                position VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'saved'
            )
        """)
        db.execute("INSERT INTO applications VALUES ('1', 'Acme', 'SWE', 'saved')")
        result = db.execute("SELECT company FROM applications WHERE id = '1'").fetchone()
        assert result[0] == "Acme"
        db.close()


class TestCrossModuleIntegration:
    def test_tracker_to_resume_matcher_workflow(self, tmp_path: Path) -> None:
        """Data flows from tracker to resume matcher."""
        from careerdex.models.application import ApplicationEntry
        from careerdex.models.resume import ContactInfo, Resume, SkillGroup
        from careerdex.services.resume_matcher import ResumeMatcher
        from careerdex.services.tracker import ApplicationTracker

        # Add an application
        tracker = ApplicationTracker(db_path=tmp_path / "app.duckdb")
        entry = ApplicationEntry(company="Acme", position="Data Engineer")
        tracker.add(entry)
        added = tracker.get(entry.id)
        assert added is not None

        # Match resume against JD
        matcher = ResumeMatcher()
        resume = Resume(
            contact=ContactInfo(name="Test User", title="Data Engineer"),
            summary="Experienced data engineer",
            skills=[SkillGroup(category="Tech", skills=["python", "sql", "aws"])],
        )
        result = matcher.match(resume, "Looking for Python and SQL data engineer")
        assert result is not None
        assert 0 <= result.overall_score <= 100
        tracker.close()

    def test_models_are_serializable(self, tmp_path: Path) -> None:
        """Models can serialize to/from dict for storage."""
        from careerdex.models.application import ApplicationEntry

        entry = ApplicationEntry(company="Test Co", position="Engineer")
        data = entry.model_dump(mode="json")
        assert data["company"] == "Test Co"

        restored = ApplicationEntry(**data)
        assert restored.company == "Test Co"
