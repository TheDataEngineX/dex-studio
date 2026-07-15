"""Prometheus metrics for dex-studio pipeline lifecycle.

Wired into jobs.py (_finalize_pipeline_run) and run_checks.py (quality scoring).
All metrics are process-level — no external dependencies beyond prometheus_client.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Pipeline execution ────────────────────────────────────────────────────────

PIPELINE_RUNS = Counter(
    "dex_pipeline_runs_total",
    "Total pipeline runs",
    ["pipeline", "status", "layer"],
)

PIPELINE_DURATION = Histogram(
    "dex_pipeline_duration_seconds",
    "Pipeline execution duration in seconds",
    ["pipeline", "layer"],
    buckets=(10, 30, 60, 120, 300, 600, 1800, 3600, 7200),
)

PIPELINE_ROWS_INPUT = Counter(
    "dex_pipeline_rows_input_total",
    "Total rows read by pipeline",
    ["pipeline", "layer"],
)

PIPELINE_ROWS_OUTPUT = Counter(
    "dex_pipeline_rows_output_total",
    "Total rows written by pipeline",
    ["pipeline", "layer"],
)

# ── Data quality ──────────────────────────────────────────────────────────────

QUALITY_SCORE = Gauge(
    "dex_data_quality_score",
    "Latest quality score for pipeline output",
    ["pipeline", "layer"],
)

QUALITY_CHECKS_FAILED = Counter(
    "dex_quality_checks_failed_total",
    "Quality checks that scored below threshold",
    ["pipeline"],
)

RECONCILIATION_MISMATCHES = Counter(
    "dex_reconciliation_mismatches_total",
    "Row count reconciliation mismatches",
    ["pipeline"],
)

# ── Queue / concurrency ───────────────────────────────────────────────────────

QUEUE_DEPTH = Gauge(
    "dex_pipeline_queue_depth",
    "Number of pipelines in queue",
    ["status"],
)

RUNNING_PIPELINES = Gauge(
    "dex_running_pipelines",
    "Number of pipelines currently executing",
)

# ── Ingestion / dedup ─────────────────────────────────────────────────────────

DEDUPLICATIONS = Counter(
    "dex_ingestion_deduplicated_total",
    "Rows skipped by content-hash dedup",
    ["source"],
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_LAYER_MAP = {
    "bronze": "bronze",
    "silver": "silver",
    "gold": "gold",
}


def _guess_layer(pipeline_name: str) -> str:
    for layer in ("bronze", "silver", "gold"):
        if pipeline_name.startswith(layer):
            return layer
    return "unknown"


def record_pipeline_run(
    pipeline: str,
    status: str,
    duration_s: float,
    rows_input: int = 0,
    rows_output: int = 0,
    layer: str = "",
) -> None:
    """Record a completed pipeline run to Prometheus."""
    if not layer:
        layer = _guess_layer(pipeline)
    PIPELINE_RUNS.labels(pipeline=pipeline, status=status, layer=layer).inc()
    PIPELINE_DURATION.labels(pipeline=pipeline, layer=layer).observe(duration_s)
    if rows_input > 0:
        PIPELINE_ROWS_INPUT.labels(pipeline=pipeline, layer=layer).inc(rows_input)
    if rows_output > 0:
        PIPELINE_ROWS_OUTPUT.labels(pipeline=pipeline, layer=layer).inc(rows_output)


def record_quality_score(pipeline: str, score: float, layer: str = "") -> None:
    """Record a quality score for a pipeline output."""
    if not layer:
        layer = _guess_layer(pipeline)
    QUALITY_SCORE.labels(pipeline=pipeline, layer=layer).set(score)


def record_quality_failure(pipeline: str) -> None:
    QUALITY_CHECKS_FAILED.labels(pipeline=pipeline).inc()


def record_reconciliation_mismatch(pipeline: str) -> None:
    RECONCILIATION_MISMATCHES.labels(pipeline=pipeline).inc()


def update_queue_depth(running: int, queued: int) -> None:
    """Update queue depth gauges."""
    RUNNING_PIPELINES.set(running)
    QUEUE_DEPTH.labels(status="running").set(running)
    QUEUE_DEPTH.labels(status="queued").set(queued)
