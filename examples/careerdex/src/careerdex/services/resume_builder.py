"""Resume builder service — Jinja2 → HTML → WeasyPrint PDF.

WeasyPrint is an optional dependency. If not installed, HTML export still works.
Install: pip install weasyprint (requires system libs: libpango, libcairo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from careerdex.models.resume import Resume

logger = structlog.get_logger()

__all__ = ["ResumeBuilder"]

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "resume.json"


class ResumeBuilder:
    """Render a Resume to HTML or PDF, and persist the data as JSON.

    Usage::

        builder = ResumeBuilder()
        html = builder.to_html(resume)
        pdf_bytes = builder.to_pdf(resume)   # requires weasyprint
    """

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    # -- Render -----------------------------------------------------------

    def to_html(self, resume: Resume) -> str:
        """Render resume to HTML string."""
        template_name = f"resume_{resume.template}.html.j2"
        # Fall back to classic if template variant not found
        try:
            tmpl = self._env.get_template(template_name)
        except Exception:
            tmpl = self._env.get_template("resume_classic.html.j2")
        html = tmpl.render(resume=resume)
        logger.info("resume_rendered_html", template=resume.template)
        return str(html)

    def to_pdf(self, resume: Resume) -> bytes:
        """Render resume to PDF bytes via WeasyPrint.

        Raises ImportError if weasyprint is not installed.
        """
        try:
            from weasyprint import HTML  # type: ignore[import-untyped, unused-ignore]
        except ImportError as exc:
            raise ImportError(
                "WeasyPrint is required for PDF export. Install with: pip install weasyprint"
            ) from exc

        html_str = self.to_html(resume)
        pdf = cast(bytes, HTML(string=html_str).write_pdf())
        logger.info("resume_rendered_pdf", size_bytes=len(pdf))
        return pdf

    # -- Persistence ------------------------------------------------------

    def save(self, resume: Resume, path: Path | None = None) -> Path:
        """Persist resume as JSON. Returns the path written."""
        dest = path or _DEFAULT_DB_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(resume.model_dump(mode="json"), indent=2), encoding="utf-8")
        logger.info("resume_saved", path=str(dest))
        return dest

    def load(self, path: Path | None = None) -> Resume | None:
        """Load resume from JSON. Returns None if file does not exist."""
        src = path or _DEFAULT_DB_PATH
        if not src.exists():
            return None
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            return Resume(**data)
        except Exception as exc:
            logger.warning("resume_load_failed", path=str(src), error=str(exc))
            return None
