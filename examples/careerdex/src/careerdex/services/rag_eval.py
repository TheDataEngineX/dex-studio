"""RAG evaluation service."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from careerdex.models.rag_eval import (
    EvaluationMetric,
    EvaluationRun,
    EvaluationStatus,
    EvaluationSummary,
    TestCase,
)

logger = structlog.get_logger(__name__)

__all__ = ["RAGEvaluationService", "run_evaluation"]

_DEFAULT_DB_PATH = Path.home() / ".dex-studio" / "careerdex" / "rag_eval.duckdb"


class RAGEvaluationService:
    """Service for evaluating RAG systems."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._init_tables()
        logger.info("rag_eval_service_ready", db=str(self._db_path))

    def _init_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR DEFAULT '',
                metrics_json VARCHAR DEFAULT '[]',
                test_cases_json VARCHAR DEFAULT '[]',
                status VARCHAR DEFAULT 'pending',
                average_scores_json VARCHAR DEFAULT '{}',
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
            """
        )

    def create_run(self, run: EvaluationRun) -> EvaluationRun:
        self._conn.execute(
            """
            INSERT INTO evaluation_runs (id, name, description, metrics_json, test_cases_json, status, average_scores_json, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,  # noqa: E501
            [
                run.id,
                run.name,
                run.description,
                json.dumps([m.value for m in run.metrics]),
                json.dumps([tc.model_dump() for tc in run.test_cases]),
                run.status.value,
                json.dumps(run.average_scores),
                run.created_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
            ],
        )
        logger.info("evaluation_run_created", id=run.id, name=run.name)
        return run

    def get_run(self, run_id: str) -> EvaluationRun | None:
        row = self._conn.execute("SELECT * FROM evaluation_runs WHERE id = ?", [run_id]).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    def list_runs(self, limit: int = 20) -> list[EvaluationRun]:
        rows = self._conn.execute(
            f"SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT {limit}"
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def update_run(self, run: EvaluationRun) -> None:
        self._conn.execute(
            """
            UPDATE evaluation_runs SET name = ?, description = ?, metrics_json = ?, test_cases_json = ?, status = ?, average_scores_json = ?, completed_at = ?
            WHERE id = ?
            """,  # noqa: E501
            [
                run.name,
                run.description,
                json.dumps([m.value for m in run.metrics]),
                json.dumps([tc.model_dump() for tc in run.test_cases]),
                run.status.value,
                json.dumps(run.average_scores),
                run.completed_at.isoformat() if run.completed_at else None,
                run.id,
            ],
        )

    def evaluate(
        self,
        run: EvaluationRun,
        retrieval_fn: Any | None = None,
        generation_fn: Any | None = None,
    ) -> EvaluationSummary:
        """Run evaluation on test cases."""
        self.create_run(run)
        run.status = EvaluationStatus.RUNNING
        self.update_run(run)

        for test_case in run.test_cases:
            if retrieval_fn:
                test_case.retrieved_context = retrieval_fn(test_case.question)
            else:
                test_case.retrieved_context = test_case.context[:2]

            if generation_fn:
                test_case.generated_answer = generation_fn(
                    test_case.question, test_case.retrieved_context
                )
            else:
                test_case.generated_answer = f"Generated answer for: {test_case.question[:50]}..."

            test_case.scores = self._compute_scores(
                test_case.question,
                test_case.ground_truth_answer,
                test_case.generated_answer,
                test_case.retrieved_context,
                run.metrics,
            )

        run.average_scores = self._compute_average_scores(run.test_cases, run.metrics)
        run.status = EvaluationStatus.COMPLETED
        run.completed_at = datetime.now()
        self.update_run(run)

        return self._generate_summary(run)

    def _compute_scores(
        self,
        question: str,
        ground_truth: str,
        generated: str,
        context: list[str],
        metrics: list[EvaluationMetric],
    ) -> dict[str, float]:
        scores = {}

        if EvaluationMetric.FAITHFULNESS in metrics:
            scores["faithfulness"] = self._compute_faithfulness(generated, context)

        if EvaluationMetric.ANSWER_RELEVANCY in metrics:
            scores["answer_relevancy"] = self._compute_answer_relevancy(question, generated)

        if EvaluationMetric.CONTEXT_RECALL in metrics:
            scores["context_recall"] = self._compute_context_recall(ground_truth, context)

        if EvaluationMetric.CONTEXT_PRECISION in metrics:
            scores["context_precision"] = self._compute_context_precision(ground_truth, context)

        if EvaluationMetric.CONTEXTRelevance in metrics:
            scores["context_relevance"] = self._compute_context_relevance(question, context)

        if EvaluationMetric.ANSWER_SIMILARITY in metrics:
            scores["answer_similarity"] = self._compute_answer_similarity(ground_truth, generated)

        if not scores:
            scores["overall"] = 0.75

        return scores

    def _compute_faithfulness(self, answer: str, context: list[str]) -> float:
        context_text = " ".join(context).lower()
        answer_words = set(answer.lower().split())
        context_words = set(context_text.split())
        overlap = len(answer_words & context_words)
        return min(overlap / max(len(answer_words), 1), 1.0)

    def _compute_answer_relevancy(self, question: str, answer: str) -> float:
        q_words = set(question.lower().split())
        a_words = set(answer.lower().split())
        overlap = len(q_words & a_words)
        return min(overlap / max(len(q_words), 1), 1.0) * 0.5 + 0.5

    def _compute_context_recall(self, ground_truth: str, context: list[str]) -> float:
        gt_words = set(ground_truth.lower().split())
        context_text = " ".join(context).lower()
        matches = sum(1 for w in gt_words if w in context_text)
        return min(matches / max(len(gt_words), 1), 1.0)

    def _compute_context_precision(self, ground_truth: str, context: list[str]) -> float:
        if not context:
            return 0.0
        gt_words = set(ground_truth.lower().split())
        total_relevant = 0.0
        for i, ctx in enumerate(context):
            ctx_words = set(ctx.lower().split())
            relevant = len(gt_words & ctx_words)
            total_relevant += relevant * (1.0 / (i + 1))
        return min(total_relevant / max(len(gt_words), 1), 1.0)

    def _compute_context_relevance(self, question: str, context: list[str]) -> float:
        q_words = set(question.lower().split())
        if not context:
            return 0.0
        total_relevant = 0
        for ctx in context:
            ctx_words = set(ctx.lower().split())
            relevant = len(q_words & ctx_words)
            total_relevant += relevant
        return min(total_relevant / (len(context) * max(len(q_words), 1)), 1.0)

    def _compute_answer_similarity(self, ground_truth: str, generated: str) -> float:
        gt_words = set(ground_truth.lower().split())
        gen_words = set(generated.lower().split())
        intersection = len(gt_words & gen_words)
        union = len(gt_words | gen_words)
        return intersection / max(union, 1)

    def _compute_average_scores(
        self, test_cases: list[TestCase], metrics: list[EvaluationMetric]
    ) -> dict[str, float]:
        if not test_cases:
            return {}

        all_scores: dict[str, list[float]] = {}
        for tc in test_cases:
            for metric, score in tc.scores.items():
                if metric not in all_scores:
                    all_scores[metric] = []
                all_scores[metric].append(score)

        averages = {}
        for metric, scores in all_scores.items():
            averages[metric] = sum(scores) / len(scores) if scores else 0.0

        return averages

    def _generate_summary(self, run: EvaluationRun) -> EvaluationSummary:
        completed_cases = [tc for tc in run.test_cases if tc.scores.get("overall", 0) > 0.5]
        failed_cases = len(run.test_cases) - len(completed_cases)

        best_case = min(run.test_cases, key=lambda tc: tc.scores.get("overall", 1), default=None)
        worst_case = max(run.test_cases, key=lambda tc: tc.scores.get("overall", 0), default=None)

        recommendations = []
        avg_scores = run.average_scores

        if avg_scores.get("faithfulness", 0) < 0.6:
            recommendations.append("Improve retrieval to include more relevant context")
        if avg_scores.get("answer_relevancy", 0) < 0.6:
            recommendations.append("Improve generation to better address the question")
        if avg_scores.get("context_recall", 0) < 0.6:
            recommendations.append("Enhance retrieval to capture more ground truth content")

        return EvaluationSummary(
            run_id=run.id,
            total_cases=len(run.test_cases),
            passed_cases=len(completed_cases),
            failed_cases=failed_cases,
            average_scores=avg_scores,
            best_case=best_case.id if best_case else None,
            worst_case=worst_case.id if worst_case else None,
            recommendations=recommendations,
        )

    def _row_to_run(self, row: tuple[object, ...]) -> EvaluationRun:
        metrics_data = json.loads(str(row[3] or "[]"))
        cases_data = json.loads(str(row[4] or "[]"))
        avg_scores = json.loads(str(row[6] or "{}"))

        return EvaluationRun(
            id=str(row[0]),
            name=str(row[1]),
            description=str(row[2] or ""),
            metrics=[EvaluationMetric(m) for m in metrics_data],
            test_cases=[TestCase(**tc) for tc in cases_data],
            status=EvaluationStatus(str(row[5])),
            average_scores=avg_scores,
            created_at=datetime.fromisoformat(str(row[7])),
            completed_at=datetime.fromisoformat(str(row[8])) if row[8] else None,
        )

    def delete_run(self, run_id: str) -> bool:
        self._conn.execute("DELETE FROM evaluation_runs WHERE id = ?", [run_id])
        return True

    def close(self) -> None:
        if self._conn:
            self._conn.close()


def run_evaluation(
    run: EvaluationRun,
    retrieval_fn: Any | None = None,
    generation_fn: Any | None = None,
) -> EvaluationSummary:
    service = RAGEvaluationService()
    return service.evaluate(run, retrieval_fn, generation_fn)
