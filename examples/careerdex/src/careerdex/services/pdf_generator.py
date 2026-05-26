"""PDF generator - generates ATS-optimized PDF resumes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

__all__ = ["PDFGenerator", "generate_pdf"]


class PDFGenerator:
    """Generate ATS-optimized PDF resumes."""

    def __init__(self) -> None:
        self._weasyprint_available = self._check_weasyprint()

    def _check_weasyprint(self) -> bool:
        """Check if WeasyPrint is available."""
        try:
            import weasyprint  # noqa: F401

            return True
        except ImportError:
            return False

    def generate(
        self,
        html_content: str,
        output_path: str | Path,
        paper_format: str = "letter",
    ) -> str:
        """Generate PDF from HTML content."""
        if self._weasyprint_available:
            return self._generate_with_weasyprint(html_content, output_path, paper_format)
        return self._generate_fallback(output_path)

    def _generate_with_weasyprint(
        self,
        html_content: str,
        output_path: str | Path,
        paper_format: str,
    ) -> str:
        """Generate PDF using WeasyPrint."""
        from weasyprint import CSS, HTML

        if paper_format == "letter":
            page_size = "letter"
            margin = "0.5in"
        else:
            page_size = "A4"
            margin = "15mm"

        base_css = CSS(
            string=f"""
            @page {{ size: {page_size}; margin: {margin}; }}
            body {{ font-family: Arial, sans-serif; font-size: 11px; line-height: 1.5; }}
            .header {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
            .section-title {{ font-size: 13px; font-weight: bold; text-transform: uppercase;
                margin-top: 15px; margin-bottom: 8px; }}
            .job-title {{ font-weight: bold; }}
            .company {{ color: #666; }}
            .skills {{ display: flex; flex-wrap: wrap; gap: 5px; }}
            .skill-tag {{ background: #eee; padding: 2px 6px; border-radius: 3px;
                font-size: 10px; }}
        """
        )

        html = HTML(string=html_content)
        html.write_css(base_css)
        html.write_pdf(str(output_path))

        return str(output_path)

    def _generate_fallback(self, output_path: str | Path) -> str:
        """Fallback when WeasyPrint not available."""
        placeholder = (
            "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj"
            "<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page"
            "/MediaBox[0 0 612 792]/Parent 2 0 R/Resources 4 0 R/Contents 5 0 R"
            ">>endobj 4 0 obj<</Font<</F1 6 0 R>>>>endobj 5 0 obj<</Length 44>>stream "
            "BT /F1 12 Tf 100 700 Td (PDF requires weasyprint) Tj ET endstream endobj "
            "6 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj xref 0 7 "
            "0000000000 65535 f 0000000009 00000 n 0000000058 00000 n 0000000115 00000 n "
            "0000000268 00000 n 0000000368 00000 n 0000000452 00000 n trailer<</Size 7"
            "/Root 1 0 R>>startxref 542 %%EOF"
        )

        with open(output_path, "w") as f:
            f.write(placeholder)

        logger.warning("Using placeholder PDF - install weasyprint for real PDFs")
        return str(output_path)

    def generate_from_template(
        self,
        resume_data: dict[str, Any],
        job_keywords: list[str],
        output_path: str | Path,
        paper_format: str = "letter",
    ) -> str:
        """Generate PDF from resume data and template."""
        html = self._build_html(resume_data, job_keywords, paper_format)
        return self.generate(html, output_path, paper_format)

    def _build_html(
        self,
        resume_data: dict[str, Any],
        keywords: list[str],
        paper_format: str,
    ) -> str:
        """Build HTML from resume data."""
        name = resume_data.get("name", "Your Name")
        email = resume_data.get("email", "")
        phone = resume_data.get("phone", "")
        location = resume_data.get("location", "")

        summary = resume_data.get("summary", "")
        experience = resume_data.get("experience", [])
        skills = resume_data.get("skills", [])

        keyword_tags = "".join(f'<span class="skill-tag">{kw}</span>' for kw in keywords[:8])

        experience_html = ""
        for exp in experience:
            bullets = "".join(f"<li>{bullet}</li>" for bullet in exp.get("bullets", []))
            experience_html += f"""
            <div class="experience-item">
                <div class="job-title">{exp.get("title", "")}</div>
                <div class="company">{exp.get("company", "")} | {exp.get("dates", "")}</div>
                <ul>{bullets}</ul>
            </div>
            """

        skills_html = "".join(f'<span class="skill-tag">{s}</span>' for s in skills)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{name} - Resume</title>
</head>
<body>
    <div class="header">{name}</div>
    <div class="contact">{email} | {phone} | {location}</div>

    <div class="section-title">Professional Summary</div>
    <p>{summary}</p>

    <div class="section-title">Core Competencies</div>
    <div class="skills">{keyword_tags}</div>

    <div class="section-title">Experience</div>
    {experience_html}

    <div class="section-title">Skills</div>
    <div class="skills">{skills_html}</div>
</body>
</html>"""


def generate_pdf(
    resume_data: dict[str, Any],
    keywords: list[str],
    output_path: str,
    paper_format: str = "letter",
) -> str:
    """Convenience function to generate PDF."""
    generator = PDFGenerator()
    return generator.generate_from_template(resume_data, keywords, output_path, paper_format)
