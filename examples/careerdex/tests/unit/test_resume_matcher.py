"""Unit tests for ResumeMatcher."""

from __future__ import annotations

from careerdex.models.resume import ContactInfo, Resume, SkillGroup, WorkExperience
from careerdex.services.resume_matcher import MatchResult, ResumeMatcher


def _make_resume(skills: list[str] | None = None, summary: str = "") -> Resume:
    skill_groups = [SkillGroup(category="Tech", skills=skills or [])]
    return Resume(
        contact=ContactInfo(name="Ada", title="Data Engineer"),
        summary=summary,
        skills=skill_groups,
    )


class TestMatchResult:
    def test_dataclass_fields(self) -> None:
        r = MatchResult(
            overall_score=75.0,
            skill_match_rate=80.0,
            missing_skills=["kubernetes"],
            matched_skills=["python"],
            keyword_matches=[("python", 3)],
            summary="Good match",
        )
        assert r.overall_score == 75.0
        assert r.skill_match_rate == 80.0
        assert r.missing_skills == ["kubernetes"]
        assert r.matched_skills == ["python"]


class TestResumeMatcher:
    def test_match_returns_result(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python", "sql"])
        result = matcher.match(resume, "We need python and sql skills.")
        assert isinstance(result, MatchResult)
        assert 0 <= result.overall_score <= 100

    def test_exact_skill_match_high_score(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python", "sql", "aws", "docker", "kubernetes"])
        jd = "Required: python, sql, aws, docker, kubernetes experience."
        result = matcher.match(resume, jd)
        assert result.skill_match_rate > 50.0

    def test_no_matching_skills_low_score(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["cobol", "fortran"])
        jd = "Required: python, sql, aws, docker, kubernetes."
        result = matcher.match(resume, jd)
        assert result.skill_match_rate < 50.0

    def test_missing_skills_populated(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        jd = "Required: python, kubernetes, terraform."
        result = matcher.match(resume, jd)
        assert len(result.missing_skills) > 0

    def test_matched_skills_populated(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        jd = "We use python and sql."
        result = matcher.match(resume, jd)
        assert "python" in result.matched_skills

    def test_empty_job_description_neutral_score(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        result = matcher.match(resume, "")
        assert result.overall_score == 50.0

    def test_summary_in_match_text(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=[], summary="Expert in python and machine learning.")
        result = matcher.match(resume, "python machine learning required")
        assert result.overall_score > 50.0

    def test_summary_strong_match(self) -> None:
        matcher = ResumeMatcher()
        _make_resume(summary="Strong match (90%).")
        assert "Strong match" in matcher._generate_summary(85.0, 80.0, ["python"], [])

    def test_summary_weak_match(self) -> None:
        matcher = ResumeMatcher()
        assert "Weak match" in matcher._generate_summary(20.0, 10.0, [], ["python", "sql"])

    def test_summary_good_match(self) -> None:
        matcher = ResumeMatcher()
        assert "Good match" in matcher._generate_summary(65.0, 60.0, ["python"], ["kubernetes"])

    def test_summary_moderate_match(self) -> None:
        matcher = ResumeMatcher()
        assert "Moderate match" in matcher._generate_summary(45.0, 40.0, ["python"], ["aws"])

    def test_experience_technologies_counted(self) -> None:
        matcher = ResumeMatcher()
        resume = Resume(
            contact=ContactInfo(name="Bob"),
            experience=[
                WorkExperience(
                    company="TechCo",
                    title="SWE",
                    technologies=["python", "spark", "kafka"],
                )
            ],
        )
        result = matcher.match(resume, "Experience with python, spark required.")
        assert "python" in result.matched_skills or result.skill_match_rate > 0

    def test_calculate_score_no_keywords_returns_fifty(self) -> None:
        matcher = ResumeMatcher()
        score = matcher._calculate_score(0.0, [], 0)
        assert score == 50.0

    def test_calculate_score_clamped_to_100(self) -> None:
        matcher = ResumeMatcher()
        score = matcher._calculate_score(100.0, [("python", 10)] * 20, 20)
        assert score <= 100.0

    def test_calculate_score_clamped_to_0(self) -> None:
        matcher = ResumeMatcher()
        score = matcher._calculate_score(0.0, [], 10)
        assert score >= 0.0

    def test_keyword_matches_limited_to_15(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=list(matcher.TECH_KEYWORDS))
        # Build a JD with many keywords
        jd = " ".join(matcher.TECH_KEYWORDS)
        result = matcher.match(resume, jd)
        assert len(result.keyword_matches) <= 15

    def test_extract_keywords_from_jd(self) -> None:
        matcher = ResumeMatcher()
        keywords = matcher._extract_keywords("We need python and sql experience.")
        assert "python" in keywords
        assert "sql" in keywords


class TestResumeMatcherEdgeCases:
    def test_case_insensitive_matching(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["PYTHON", "SQL"])
        result = matcher.match(resume, "python sql required")
        assert result.skill_match_rate > 0

    def test_partial_keyword_match(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        result = matcher.match(resume, "pythoning experience")
        assert len(result.matched_skills) > 0

    def test_empty_resume_skills(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=[])
        result = matcher.match(resume, "python sql required")
        assert result.skill_match_rate < 50.0

    def test_very_long_job_description(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        long_jd = "Python " * 100
        result = matcher.match(resume, long_jd)
        assert isinstance(result, MatchResult)

    def test_special_chars_in_jd(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["c++", "c#"])
        result = matcher.match(resume, "C++ and C# required")
        assert result.skill_match_rate > 0

    def test_unicode_skills(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python"])
        result = matcher.match(resume, "python required 日本語")
        assert isinstance(result, MatchResult)

    def test_numbers_in_keywords(self) -> None:
        matcher = ResumeMatcher()
        resume = _make_resume(skills=["python3", "sql2022"])
        result = matcher.match(resume, "python3 sql2022 experience")
        assert isinstance(result, MatchResult)
