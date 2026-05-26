"""CLI entry point for CareerDEX.

Usage::

    careerdex                    # Start web UI
    careerdex scan --query <q> # Scan job listings
    careerdex match <resume>   # Match resume to jobs
    careerdex export pdf       # Export to PDF
    careerdex --version       # Print version
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="careerdex",
        description="CareerDEX — AI-powered career intelligence built on DataEngineX",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan job listings")
    scan_parser.add_argument(
        "--query",
        default="data engineer",
        help="Job search query",
    )
    scan_parser.add_argument(
        "--location",
        default="Remote",
        help="Job location",
    )
    scan_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max jobs to fetch",
    )
    scan_parser.add_argument(
        "--source",
        default="linkedin",
        choices=["linkedin", "indeed", "all"],
        help="Job source to scan",
    )

    # match command
    match_parser = subparsers.add_parser("match", help="Match resume to jobs")
    match_parser.add_argument(
        "resume",
        type=Path,
        help="Path to resume PDF",
    )
    match_parser.add_argument(
        "--jobs",
        type=int,
        default=10,
        help="Number of matching jobs to return",
    )

    # export command
    export_parser = subparsers.add_parser("export", help="Export data")
    export_parser.add_argument(
        "format",
        choices=["pdf", "csv", "json"],
        help="Export format",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        default=Path("careerdex_export"),
        help="Output file path (without extension)",
    )

    # version flag
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from careerdex import __version__

        print(f"careerdex {__version__}")  # noqa: T201
        sys.exit(0)

    if args.command == "scan":
        _run_scan(args)
    elif args.command == "match":
        _run_match(args)
    elif args.command == "export":
        _run_export(args)
    else:
        _run_ui()


def _run_scan(args: argparse.Namespace) -> None:
    """Run job scan."""
    from careerdex.models.job import JobSearchQuery
    from careerdex.services.job_search import JobSearchService

    svc = JobSearchService()
    query = JobSearchQuery(
        keywords=getattr(args, "query", "data engineer"),
        location=str(getattr(args, "location", "") or ""),
        max_results=getattr(args, "limit", 20),
    )
    jobs = svc.search(query)
    print(f"Found {len(jobs)} jobs")
    for job in jobs[:5]:
        print(f"  - {job.title} @ {job.company}")


def _run_match(args: argparse.Namespace) -> None:
    """Match resume to jobs."""
    print(f"Matching {args.resume} to top {args.jobs} jobs...")
    print("Resume matching not yet implemented")


def _run_export(args: argparse.Namespace) -> None:
    """Export data."""
    print(f"Exporting to {args.format}...")
    print("Export not yet implemented")


def _run_ui() -> None:
    """Start the CareerDEX web UI via Reflex."""
    import os
    import shutil

    reflex = shutil.which("reflex")
    if reflex is None:
        sys.stderr.write("Error: reflex not found in PATH\n")
        sys.exit(1)
    os.execvp(reflex, [reflex, "run", "--env", "prod"])


if __name__ == "__main__":
    main()
