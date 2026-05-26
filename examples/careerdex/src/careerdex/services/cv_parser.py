"""CV parser — extracts text from PDF/DOCX files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

__all__ = ["parse_cv", "extract_sections"]

SECTION_PATTERNS = {
    "experience": r"(?i)(experience|work history|employment)",
    "education": r"(?i)(education|degree|certification)",
    "skills": r"(?i)(skills|technologies|technical)",
    "projects": r"(?i)(projects|portfolio)",
}


def extract_sections(text: str) -> dict[str, str]:
    """Extract sections from CV text."""
    sections = {}
    lines = text.split("\n")
    current_section = "header"
    current_content: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        matched = False
        for section, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, line):
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = section
                current_content = []
                matched = True
                break

        if not matched:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content)

    return sections


def parse_cv(file_path: str | Path) -> str:
    """Extract text from CV file."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {path}")

    text = ""

    if path.suffix.lower() == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(path)
            text = "\n".join(page.extract_text() for page in reader.pages)
        except ImportError:
            text = "PDF parsing not available - install pypdf"
    elif path.suffix.lower() in [".docx", ".doc"]:
        try:
            import docx

            doc = docx.Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            text = "DOCX parsing not available - install python-docx"
    elif path.suffix.lower() == ".txt":
        text = path.read_text()
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    return text


def parse_cv_text(text: str) -> dict[str, Any]:
    """Parse CV text into structured data."""
    sections = extract_sections(text)

    return {
        "raw_text": text,
        "sections": sections,
        "word_count": len(text.split()),
        "line_count": len(text.split("\n")),
    }
