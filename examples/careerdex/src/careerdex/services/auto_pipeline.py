"""Auto-pipeline service — combines evaluation + PDF + tracker in one flow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import structlog

from careerdex.models.application import ApplicationEntry, ApplicationStatus
from careerdex.models.evaluation import JobEvaluation
from careerdex.services.job_evaluator import JobEvaluator
from careerdex.services.pdf_generator import PDFGenerator
from careerdex.services.tracker import ApplicationTracker

logger = structlog.get_logger()

__all__ = ["AutoPipeline", "run_auto_pipeline"]


class PipelineResult:
    """Result of an auto-pipeline run."""

    def __init__(
        self,
        evaluation: JobEvaluation,
        application: ApplicationEntry,
        pdf_path: str | None = None,
    ):
        self.evaluation = evaluation
        self.application = application
        self.pdf_path = pdf_path


class AutoPipeline:
    """Orchestrates the full auto-pipeline: evaluate + PDF + tracker."""

    def __init__(
        self,
        cv_path: Path | None = None,
        db_path: Path | None = None,
    ):
        self.cv_path = cv_path
        self.tracker = ApplicationTracker(db_path)
        self._cv_text: str | None = None

    def _load_cv(self) -> str:
        """Load CV text from file."""
        if self._cv_text:
            return self._cv_text
        if self.cv_path and self.cv_path.exists():
            self._cv_text = self.cv_path.read_text()
        else:
            self._cv_text = ""
        return self._cv_text

    def run(
        self,
        job_description: str,
        url: str = "",
        auto_save: bool = True,
    ) -> PipelineResult:
        """Run the full auto-pipeline."""
        logger.info("auto_pipeline_started", url=url)

        cv_text = self._load_cv()

        evaluator = JobEvaluator(cv_text)
        evaluation = evaluator.evaluate(job_description)

        company, position = evaluator._extract_company_role(job_description)

        app_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        application = ApplicationEntry(
            id=app_id,
            company=company,
            position=position,
            url=url,
            status=ApplicationStatus.SAVED,
            source="auto-pipeline",
            created_at=now,
            updated_at=now,
        )

        if evaluation.overall_grade in ["A", "B"]:
            application.status = ApplicationStatus.REACHED_OUT

        if auto_save:
            self.tracker.add(application)
            logger.info("application_added", id=app_id, company=company)

        pdf_path: str | None = None
        if evaluation.overall_grade in ["A", "B", "C"]:
            try:
                if cv_text:
                    html_content = f"""
                    <div class="header">
                        <h1>Candidate Resume</h1>
                        <p>Applied to: {position} at {company}</p>
                    </div>
                    <div class="content">
                        <pre>{cv_text[:2000]}</pre>
                    </div>
                    """

                    output_dir = Path.home() / ".dex-studio" / "careerdex" / "output"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"cv_{company}_{position}.pdf"

                    pdf_gen = PDFGenerator()
                    pdf_path = pdf_gen.generate(
                        html_content=html_content,
                        output_path=str(output_path),
                    )
                    logger.info("pdf_generated", path=str(pdf_path))
            except Exception as e:
                logger.warning("pdf_generation_failed", error=str(e))

        logger.info(
            "auto_pipeline_completed",
            app_id=app_id,
            grade=evaluation.overall_grade,
            pdf_generated=pdf_path is not None,
        )

        return PipelineResult(
            evaluation=evaluation,
            application=application,
            pdf_path=pdf_path,
        )


def run_auto_pipeline(
    job_description: str,
    url: str = "",
    cv_path: Path | None = None,
) -> PipelineResult:
    """Convenience function to run the auto-pipeline."""
    pipeline = AutoPipeline(cv_path=cv_path)
    return pipeline.run(job_description, url)
