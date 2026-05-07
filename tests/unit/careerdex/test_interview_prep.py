"""Unit tests for InterviewPrepService."""

from __future__ import annotations

import json
import unittest.mock

import httpx
import pytest
from careerdex.services.interview_prep import InterviewPrepService, Question


@pytest.fixture()
def svc() -> InterviewPrepService:
    return InterviewPrepService()


class TestQuestion:
    def test_defaults_from_empty_dict(self) -> None:
        q = Question({})
        assert q.id == ""
        assert q.question == ""
        assert q.category == ""
        assert q.difficulty == "medium"
        assert q.tags == []
        assert q.hints == []
        assert q.sample_answer == ""
        assert q.star_components == {}

    def test_type_behavioral_when_star_present(self) -> None:
        star = {"situation": "s", "task": "t", "action": "a", "result": "r"}
        q = Question({"star_components": star})
        assert q.type == "behavioral"

    def test_type_technical_when_no_star(self) -> None:
        q = Question({"question": "What is a JOIN?"})
        assert q.type == "technical"

    def test_full_fields(self) -> None:
        data = {
            "id": "q1",
            "question": "Explain Spark.",
            "category": "Spark",
            "difficulty": "hard",
            "tags": ["spark", "distributed"],
            "hints": ["Think DAG"],
            "sample_answer": "Spark is...",
        }
        q = Question(data)
        assert q.id == "q1"
        assert q.category == "Spark"
        assert q.difficulty == "hard"
        assert "spark" in q.tags


class TestInterviewPrepServiceLoad:
    def test_loads_questions(self, svc: InterviewPrepService) -> None:
        assert len(svc.all_questions) > 0

    def test_all_questions_are_question_instances(self, svc: InterviewPrepService) -> None:
        for q in svc.all_questions:
            assert isinstance(q, Question)

    def test_categories_non_empty(self, svc: InterviewPrepService) -> None:
        cats = svc.categories
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_categories_no_duplicates(self, svc: InterviewPrepService) -> None:
        cats = svc.categories
        assert len(cats) == len(set(cats))

    def test_has_behavioral_questions(self, svc: InterviewPrepService) -> None:
        behavioral = [q for q in svc.all_questions if q.type == "behavioral"]
        assert len(behavioral) > 0

    def test_has_technical_questions(self, svc: InterviewPrepService) -> None:
        technical = [q for q in svc.all_questions if q.type == "technical"]
        assert len(technical) > 0


class TestFilter:
    def test_filter_by_type_behavioral(self, svc: InterviewPrepService) -> None:
        results = svc.filter(qtype="behavioral")
        assert all(q.type == "behavioral" for q in results)

    def test_filter_by_type_technical(self, svc: InterviewPrepService) -> None:
        results = svc.filter(qtype="technical")
        assert all(q.type == "technical" for q in results)

    def test_filter_by_difficulty(self, svc: InterviewPrepService) -> None:
        results = svc.filter(difficulty="medium")
        assert all(q.difficulty == "medium" for q in results)

    def test_filter_by_category_case_insensitive(self, svc: InterviewPrepService) -> None:
        first_cat = svc.categories[0]
        results_lower = svc.filter(category=first_cat.lower())
        results_upper = svc.filter(category=first_cat.upper())
        assert len(results_lower) == len(results_upper)

    def test_filter_by_tag(self, svc: InterviewPrepService) -> None:
        # Get a tag from the first question that has tags
        tagged = [q for q in svc.all_questions if q.tags]
        if tagged:
            tag = tagged[0].tags[0]
            results = svc.filter(tag=tag)
            assert all(tag.lower() in [t.lower() for t in q.tags] for q in results)

    def test_no_filter_returns_all(self, svc: InterviewPrepService) -> None:
        assert len(svc.filter()) == len(svc.all_questions)

    def test_unknown_type_returns_empty(self, svc: InterviewPrepService) -> None:
        assert svc.filter(qtype="nonexistent") == []


class TestRandomQuestion:
    def test_returns_question_or_none(self, svc: InterviewPrepService) -> None:
        q = svc.random_question()
        assert q is None or isinstance(q, Question)

    def test_returns_question(self, svc: InterviewPrepService) -> None:
        # With real question bank loaded, should return something
        q = svc.random_question()
        assert q is not None

    def test_filter_respected(self, svc: InterviewPrepService) -> None:
        q = svc.random_question(qtype="behavioral")
        if q is not None:
            assert q.type == "behavioral"

    def test_impossible_filter_returns_none(self, svc: InterviewPrepService) -> None:
        q = svc.random_question(qtype="nonexistent_type_xyz")
        assert q is None


class TestScore:
    def _mock_question(self) -> Question:
        return Question(
            {
                "id": "test_q",
                "question": "Explain data pipelines.",
                "category": "Data Engineering",
            }
        )

    def test_score_success(self, svc: InterviewPrepService) -> None:
        q = self._mock_question()
        feedback_json = json.dumps(
            {
                "score": 7,
                "strengths": ["clear explanation"],
                "improvements": ["more detail"],
                "missing_points": [],
                "verdict": "Good answer",
            }
        )

        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"response": feedback_json}
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch("httpx.post", return_value=mock_resp):
            result = svc.score(q, "Pipelines move data from A to B.")

        assert result["score"] == 7
        assert "strengths" in result
        assert "verdict" in result

    def test_score_strips_markdown_fence(self, svc: InterviewPrepService) -> None:
        q = self._mock_question()
        feedback_json = json.dumps(
            {
                "score": 5,
                "strengths": [],
                "improvements": [],
                "missing_points": [],
                "verdict": "ok",
            }
        )
        wrapped = f"```json\n{feedback_json}\n```"

        mock_resp = unittest.mock.MagicMock()
        mock_resp.json.return_value = {"response": wrapped}
        mock_resp.raise_for_status.return_value = None

        with unittest.mock.patch("httpx.post", return_value=mock_resp):
            result = svc.score(q, "Answer")

        assert result["score"] == 5

    def test_score_raises_on_connection_error(self, svc: InterviewPrepService) -> None:
        q = self._mock_question()
        err = httpx.ConnectError("refused")
        with (
            unittest.mock.patch("httpx.post", side_effect=err),
            pytest.raises(httpx.ConnectError),
        ):
            svc.score(q, "Answer")
