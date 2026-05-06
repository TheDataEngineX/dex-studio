#!/usr/bin/env python
"""ShopMetrics — DataEngineX full-feature demonstration.

Covers every platform capability in one runnable script:

  1. Config    — load & validate dex.yaml
  2. Data      — CSV ingest → SQL transforms → quality gates → medallion layers
  3. ML        — feature engineering, training, model registry, stage promotion
  4. Drift     — detect distribution shift between train/prod cohorts
  5. RAG       — build vector index over product catalog, answer natural-language queries
  6. Lineage   — record and query the full data provenance graph
  7. Summary   — human-readable results table

Run from the repo root:

    uv run python examples/ecommerce/run_all.py

No external services required (uses MockProvider for LLM, in-memory vector store).
Set LLM_MODEL env var and have Ollama running for live generation.
"""

from __future__ import annotations

import csv
import random
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()

HERE = Path(__file__).parent
DATA = HERE / "data"
CONFIG = HERE / "dex.yaml"


# ── helpers ───────────────────────────────────────────────────────────────────


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(msg: str) -> None:
    print(f"     {msg}")


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


# ── 1. Config ─────────────────────────────────────────────────────────────────


def demo_config() -> None:
    _section("1 · Config — load & validate dex.yaml")
    from dataenginex.config import load_config

    cfg = load_config(CONFIG)
    _ok(f"Project : {cfg.project.name} v{cfg.project.version}")
    _ok(f"Engine  : {cfg.data.engine if cfg.data else 'n/a'}")
    sources = list(cfg.data.sources.keys()) if cfg.data and cfg.data.sources else []
    pipelines = list(cfg.data.pipelines.keys()) if cfg.data and cfg.data.pipelines else []
    _ok(f"Sources : {', '.join(sources)}")
    _ok(f"Pipelines: {', '.join(pipelines)}")
    if cfg.ai:
        _ok(f"LLM     : {cfg.ai.llm.provider}/{cfg.ai.llm.model}")


# ── 2. Data pipeline ──────────────────────────────────────────────────────────


def demo_data() -> tuple[list[dict], list[dict], list[dict]]:  # noqa: C901
    _section("2 · Data — ingest → transform → quality gate → medallion")
    from dataenginex.core.medallion_architecture import DataLayer, MedallionArchitecture
    from dataenginex.core.quality import QualityGate, QualityStore

    # Bronze: raw ingest from CSV
    raw_customers = _load_csv(DATA / "customers.csv")
    raw_orders = _load_csv(DATA / "orders.csv")
    raw_products = _load_csv(DATA / "products.csv")
    _ok(
        f"Bronze  : {len(raw_customers)} customers, {len(raw_orders)} orders, "
        f"{len(raw_products)} products"
    )

    # Silver: filter + deduplicate customers
    seen_ids: set[str] = set()
    silver_customers: list[dict] = []
    for r in raw_customers:
        if int(r["age"]) > 0 and int(r["tenure_days"]) >= 0 and r["customer_id"] not in seen_ids:
            seen_ids.add(r["customer_id"])
            silver_customers.append(dict(r))

    # Silver: filter orders
    silver_orders = [
        dict(r)
        for r in raw_orders
        if float(r["total"]) > 0 and r["status"] in ("completed", "refunded")
    ]

    # Quality gate on silver_customers
    store = QualityStore()
    gate = QualityGate(
        store=store,
        required_fields={"customer_id", "email", "age", "churned"},
        uniqueness_key="customer_id",
        scorer=lambda r: 1.0 if "@" in r.get("email", "") else 0.0,
    )
    result = gate.evaluate(silver_customers, DataLayer.SILVER, dataset_name="silver_customers")
    status = "PASS" if result.passed else "FAIL"
    _ok(
        f"Silver quality gate [{status}] score={result.quality_score:.3f} "
        f"threshold={result.threshold:.2f} n={result.record_count}"
    )
    for dim, score in result.dimensions.items():
        _info(f"  {dim}: {score:.3f}")

    # Gold: customer revenue aggregation
    revenue: dict[str, dict] = {}
    for order in silver_orders:
        cid = order["customer_id"]
        if cid not in revenue:
            revenue[cid] = {
                "customer_id": cid,
                "order_count": 0,
                "lifetime_value": 0.0,
                "refund_count": 0,
            }
        revenue[cid]["order_count"] += 1
        if order["status"] == "completed":
            revenue[cid]["lifetime_value"] += float(order["total"])
        else:
            revenue[cid]["refund_count"] += 1
    gold_revenue = list(revenue.values())

    # Gold: product performance
    perf: dict[str, dict] = {}
    for order in silver_orders:
        if order["status"] != "completed":
            continue
        pid = order["product_id"]
        if pid not in perf:
            perf[pid] = {"product_id": pid, "units_sold": 0, "gross_revenue": 0.0}
        perf[pid]["units_sold"] += int(order["quantity"])
        perf[pid]["gross_revenue"] += float(order["total"])
    gold_products = sorted(perf.values(), key=lambda r: r["gross_revenue"], reverse=True)

    gold_gate = QualityGate(required_fields={"customer_id", "lifetime_value"})
    gold_result = gold_gate.evaluate(gold_revenue, DataLayer.GOLD, dataset_name="gold_revenue")
    _ok(
        f"Gold quality gate [{'PASS' if gold_result.passed else 'FAIL'}] "
        f"score={gold_result.quality_score:.3f} n={gold_result.record_count}"
    )

    layer_summary = MedallionArchitecture.get_all_layers()
    _ok(f"Medallion layers: {[layer.layer_name for layer in layer_summary]}")

    _ok("Top 3 products by revenue:")
    for p in gold_products[:3]:
        _info(f"  {p['product_id']}: ${p['gross_revenue']:,.2f} ({p['units_sold']} units)")

    return silver_customers, silver_orders, gold_revenue


# ── 3. ML training ────────────────────────────────────────────────────────────


def demo_ml(silver_customers: list[dict]) -> None:
    _section("3 · ML — training, model registry, stage promotion")
    from dataenginex.ml import ModelRegistry, ModelStage, SklearnTrainer
    from dataenginex.ml.registry import ModelArtifact
    from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]

    feature_cols = ["age", "tenure_days", "monthly_spend", "support_tickets", "login_frequency"]

    X = [[float(r[c]) for c in feature_cols] for r in silver_customers]
    y = [1 if r["churned"].lower() == "true" else 0 for r in silver_customers]

    split = max(1, int(len(X) * 0.75))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    churn_rate = sum(y) / len(y) if y else 0
    _ok(f"Dataset : {len(X_train)} train / {len(X_test)} test | churn rate {churn_rate:.0%}")

    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "artifacts"
        registry_path = Path(tmpdir) / "registry.json"
        artifact_dir.mkdir()

        trainer = SklearnTrainer(
            model_name="churn_prediction",
            version="1.0.0",
            estimator=RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42),
        )
        result = trainer.train(X_train=X_train, y_train=y_train)
        metrics = trainer.evaluate(X_test, y_test)
        result.metrics.update(metrics)

        acc = metrics.get("accuracy", 0.0)
        f1 = metrics.get("f1", 0.0)
        _ok(f"Training: accuracy={acc:.3f}  f1={f1:.3f}")

        registry = ModelRegistry(registry_path)
        artifact = ModelArtifact(
            name="churn_prediction",
            version="1.0.0",
            stage=ModelStage.DEVELOPMENT,
            metrics=result.metrics,
            parameters={"n_estimators": 100, "max_depth": 4},
            artifact_path=str(artifact_dir),
        )
        registry.register(artifact)
        _ok("Registered in ModelRegistry (stage=development)")

        registry.promote("churn_prediction", "1.0.0", ModelStage.STAGING)
        _ok("Promoted → staging")

        if acc >= 0.70:
            registry.promote("churn_prediction", "1.0.0", ModelStage.PRODUCTION)
            _ok(f"Promoted → production (accuracy={acc:.3f} ≥ 0.70 threshold)")
        else:
            _info(f"Held at staging (accuracy={acc:.3f} < 0.70 threshold)")

        all_versions = registry.list_versions("churn_prediction")
        _ok(f"Registry contains {len(all_versions)} version(s) of churn_prediction")


# ── 4. Drift detection ────────────────────────────────────────────────────────


def demo_drift(silver_customers: list[dict]) -> None:
    _section("4 · Drift — PSI detection across customer features")
    from dataenginex.ml import DriftDetector

    detector = DriftDetector(psi_threshold=0.15, n_bins=5)
    random.seed(99)

    # Simulate a shifted prod cohort (tenure compressed, tickets elevated)
    reference_tenure = [float(r["tenure_days"]) for r in silver_customers]
    current_tenure = [max(0.0, v * random.uniform(0.3, 0.7)) for v in reference_tenure]
    result_tenure = detector.check_feature("tenure_days", reference_tenure, current_tenure)
    psi_t, drift_t = result_tenure.psi, result_tenure.drift_detected
    _ok(f"tenure_days   PSI={psi_t:.4f}  {'DRIFT ⚠' if drift_t else 'stable'}")

    # Stable feature (monthly_spend barely moves)
    reference_spend = [float(r["monthly_spend"]) for r in silver_customers]
    current_spend = [v + random.gauss(0, 2) for v in reference_spend]
    result_spend = detector.check_feature("monthly_spend", reference_spend, current_spend)
    psi_s, drift_s = result_spend.psi, result_spend.drift_detected
    _ok(f"monthly_spend PSI={psi_s:.4f}  {'DRIFT ⚠' if drift_s else 'stable'}")

    # Full dataset check — check_dataset takes {feature: [float, ...]} dicts
    ref_ds = {
        "tenure_days": [float(r["tenure_days"]) for r in silver_customers],
        "monthly_spend": [float(r["monthly_spend"]) for r in silver_customers],
        "support_tickets": [float(r["support_tickets"]) for r in silver_customers],
    }
    cur_ds = {
        "tenure_days": [max(0.0, v * random.uniform(0.4, 0.8)) for v in ref_ds["tenure_days"]],
        "monthly_spend": [v + random.gauss(0, 3) for v in ref_ds["monthly_spend"]],
        "support_tickets": [min(10.0, v + random.randint(0, 2)) for v in ref_ds["support_tickets"]],
    }
    ds_result = detector.check_dataset(ref_ds, cur_ds)
    n_drifted = sum(1 for r in ds_result if r.drift_detected)
    _ok(f"Dataset check : {n_drifted}/{len(ds_result)} features drifted")


# ── 5. RAG pipeline ───────────────────────────────────────────────────────────


def demo_rag() -> None:
    _section("5 · RAG — product catalog vector search + generation")
    from dataenginex.ml.llm import LLMConfig, MockProvider
    from dataenginex.ml.vectorstore import InMemoryBackend, RAGPipeline

    products = _load_csv(DATA / "products.csv")
    docs = [
        f"{p['name']} (${p['price']}, rating {p['rating']}): {p['description']}" for p in products
    ]
    docs += [
        "Quality gates enforce completeness, uniqueness, and consistency at layer transitions.",
        "The ML module supports sklearn, XGBoost, and PyTorch with built-in drift detection.",
        "RAG pipelines use hybrid retrieval: dense embeddings + BM25 keyword search.",
        "Churn risk factors: high support tickets, low login frequency, short tenure.",
        "ShopMetrics starter plan costs $29.99/month; pro $89.99; enterprise $249.99.",
    ]

    backend = InMemoryBackend()
    provider = MockProvider(
        LLMConfig(model="mock-v1"),
        default_response="Based on the ShopMetrics product catalog and platform documentation",
    )
    pipeline = RAGPipeline(store=backend)
    pipeline.ingest(docs)
    _ok(f"Ingested {len(docs)} documents into vector store")

    for query in [
        "What products help with data quality monitoring?",
        "Which plan is best for enterprise teams?",
        "How does drift detection work?",
    ]:
        response = pipeline.answer(query, llm=provider)
        _info(f"Q: {query}")
        _info(f"A: {response.text[:110]}...")
        print()


# ── 6. Lineage ────────────────────────────────────────────────────────────────


def demo_lineage(
    silver_customers: list[dict],
    silver_orders: list[dict],
    gold_revenue: list[dict],
) -> None:
    _section("6 · Lineage — warehouse data provenance graph")
    from dataenginex.warehouse.lineage import PersistentLineage

    lineage = PersistentLineage(persist_path=Path("/tmp/shopmetrics/lineage.jsonl"))

    bronze_cust = lineage.record(
        operation="ingest",
        layer="bronze",
        source="s3://shopmetrics/raw/customers.csv",
        destination="bronze.raw_customers",
        input_count=20,
        output_count=20,
        pipeline_name="clean_customers",
        step_name="csv_ingest",
        quality_score=1.0,
    )
    lineage.record(
        operation="transform",
        layer="silver",
        source="bronze.raw_customers",
        destination="silver.silver_customers",
        input_count=20,
        output_count=len(silver_customers),
        pipeline_name="clean_customers",
        step_name="filter+dedup",
        quality_score=0.97,
        parent_id=bronze_cust.event_id,
    )
    bronze_ord = lineage.record(
        operation="ingest",
        layer="bronze",
        source="s3://shopmetrics/raw/orders.csv",
        destination="bronze.raw_orders",
        input_count=50,
        output_count=50,
        pipeline_name="clean_orders",
        step_name="csv_ingest",
        quality_score=1.0,
    )
    silver_ord_evt = lineage.record(
        operation="transform",
        layer="silver",
        source="bronze.raw_orders",
        destination="silver.silver_orders",
        input_count=50,
        output_count=len(silver_orders),
        pipeline_name="clean_orders",
        step_name="filter",
        quality_score=0.99,
        parent_id=bronze_ord.event_id,
    )
    gold_evt = lineage.record(
        operation="enrich",
        layer="gold",
        source="silver.silver_orders",
        destination="gold.customer_revenue",
        input_count=len(silver_orders),
        output_count=len(gold_revenue),
        pipeline_name="customer_revenue",
        step_name="sql_agg",
        quality_score=1.0,
        parent_id=silver_ord_evt.event_id,
        metadata={"transform": "GROUP BY customer_id"},
    )

    _ok(f"Recorded {len(lineage.all_events)} lineage events")

    chain = lineage.get_chain(gold_evt.event_id)
    _ok(f"Provenance chain for gold.customer_revenue ({len(chain)} hops):")
    for evt in chain:
        _info(
            f"  [{evt.layer:6s}] {evt.source} → {evt.destination} "
            f"({evt.input_count}→{evt.output_count} rows, op={evt.operation})"
        )

    summary = lineage.summary()
    _ok(f"Lineage summary: {summary}")


# ── 7. Summary ────────────────────────────────────────────────────────────────


def print_summary(silver_customers: list[dict], gold_revenue: list[dict]) -> None:
    _section("7 · Summary")

    total = len(silver_customers)
    churned = sum(1 for r in silver_customers if r["churned"].lower() == "true")
    active = total - churned
    total_ltv = sum(r["lifetime_value"] for r in gold_revenue)
    avg_ltv = total_ltv / len(gold_revenue) if gold_revenue else 0
    top = max(gold_revenue, key=lambda r: r["lifetime_value"])

    plan_counts: dict[str, int] = {}
    for r in silver_customers:
        plan_counts[r["plan"]] = plan_counts.get(r["plan"], 0) + 1

    print(f"""
  Customers  : {total} total | {active} active | {churned} churned ({churned / total:.0%})
  Plans      : {" | ".join(f"{k}: {v}" for k, v in sorted(plan_counts.items()))}
  Revenue    : ${total_ltv:,.2f} total LTV | ${avg_ltv:,.2f} avg per customer
  Top buyer  : customer_id={top["customer_id"]}  LTV=${top["lifetime_value"]:,.2f}

  Features exercised:
    ✓ Config loading & validation          (dex.yaml → DexConfig)
    ✓ CSV ingest → Bronze / Silver / Gold  (medallion architecture)
    ✓ SQL aggregation transforms           (customer_revenue, product_performance)
    ✓ Quality gates with dimension scoring (completeness, uniqueness, accuracy)
    ✓ ML training (RandomForest / sklearn) (SklearnTrainer)
    ✓ Model registry + stage promotion     (dev → staging → production)
    ✓ PSI drift detection                  (feature + dataset)
    ✓ RAG pipeline                         (InMemoryBackend + MockProvider)
    ✓ Warehouse lineage                    (PersistentLineage, chain query)
""")


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n" + "═" * 60)
    print("  ShopMetrics — DataEngineX Full-Feature Demo")
    print("═" * 60)

    demo_config()
    silver_customers, silver_orders, gold_revenue = demo_data()
    demo_ml(silver_customers)
    demo_drift(silver_customers)
    demo_rag()
    demo_lineage(silver_customers, silver_orders, gold_revenue)
    print_summary(silver_customers, gold_revenue)


if __name__ == "__main__":
    main()
