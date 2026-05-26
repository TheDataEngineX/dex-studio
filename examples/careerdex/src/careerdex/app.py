"""CareerDEX web app."""

from __future__ import annotations

import reflex as rx

from careerdex.pages.career.analytics import analytics_page
from careerdex.pages.career.applications import applications_page
from careerdex.pages.career.courses import courses_page
from careerdex.pages.career.cover_letter import cover_letter_page
from careerdex.pages.career.dashboard import career_dashboard
from careerdex.pages.career.discover import discover_page
from careerdex.pages.career.evaluate import evaluate_page
from careerdex.pages.career.interview import interview_page
from careerdex.pages.career.jobs import jobs_page
from careerdex.pages.career.negotiate import negotiate_page
from careerdex.pages.career.network import network_page
from careerdex.pages.career.networking import networking_page
from careerdex.pages.career.pdf_export import pdf_export_page
from careerdex.pages.career.pipeline import pipeline_page
from careerdex.pages.career.prep import prep_page
from careerdex.pages.career.profile import profile_page
from careerdex.pages.career.progress import progress_page
from careerdex.pages.career.projects import projects_page
from careerdex.pages.career.research import research_page
from careerdex.pages.career.resume import resume_page
from careerdex.pages.career.resume_matcher import resume_matcher_page
from careerdex.pages.career.scanner import scanner_page
from careerdex.pages.career.stories import stories_page
from careerdex.state.career import CareerState

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        gray_color="slate",
        radius="medium",
    ),
    stylesheets=[
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Poppins:wght@600;700&display=swap",
    ],
    style={"font_family": "Inter, system-ui, -apple-system, sans-serif"},
)

# Overview
app.add_page(career_dashboard, route="/", on_load=CareerState.init)
app.add_page(analytics_page, route="/analytics", on_load=CareerState.init)

# Job Search
app.add_page(discover_page, route="/discover", on_load=CareerState.init)
app.add_page(scanner_page, route="/scanner", on_load=CareerState.init)
app.add_page(jobs_page, route="/jobs", on_load=CareerState.init)
app.add_page(applications_page, route="/applications", on_load=CareerState.init)
app.add_page(pipeline_page, route="/pipeline", on_load=CareerState.init)

# Prepare
app.add_page(profile_page, route="/profile", on_load=CareerState.init)
app.add_page(resume_page, route="/resume", on_load=CareerState.init)
app.add_page(resume_matcher_page, route="/resume-matcher", on_load=CareerState.init)
app.add_page(cover_letter_page, route="/cover-letter", on_load=CareerState.init)
app.add_page(pdf_export_page, route="/pdf-export", on_load=CareerState.init)

# Prep
app.add_page(prep_page, route="/prep", on_load=CareerState.init)
app.add_page(interview_page, route="/interview", on_load=CareerState.init)
app.add_page(stories_page, route="/stories", on_load=CareerState.init)
app.add_page(evaluate_page, route="/evaluate", on_load=CareerState.init)
app.add_page(research_page, route="/research", on_load=CareerState.init)
app.add_page(negotiate_page, route="/negotiate", on_load=CareerState.init)

# Network
app.add_page(network_page, route="/network", on_load=CareerState.init)
app.add_page(networking_page, route="/networking", on_load=CareerState.init)
app.add_page(progress_page, route="/progress", on_load=CareerState.init)
app.add_page(courses_page, route="/courses", on_load=CareerState.init)
app.add_page(projects_page, route="/projects", on_load=CareerState.init)
