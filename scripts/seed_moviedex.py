"""Seed MovieDEX with realistic demo data — runs pipelines, logs experiments, registers models."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the dex-studio package is importable
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parents[2] / "dex" / "src"))

from dataenginex.engine import DexEngine
from dataenginex.ml.registry import ModelArtifact, ModelStage

CONFIG = Path(__file__).parents[1] / "examples" / "movie-dex" / "dex.yaml"

_PIPELINES = ["load_movies", "process_ratings", "load_credits", "genre_analysis"]

_EXPERIMENT_RUNS = [
    (
        "baseline_cf",
        {"algorithm": "collaborative_filter", "n_factors": 20},
        {"rmse": 0.921, "mae": 0.703, "precision_at_10": 0.31},
    ),
    (
        "svd_tuned",
        {"algorithm": "SVD", "n_factors": 50, "n_epochs": 30},
        {"rmse": 0.847, "mae": 0.654, "precision_at_10": 0.38},
    ),
    (
        "hybrid_model",
        {"algorithm": "hybrid", "content_weight": 0.3, "cf_weight": 0.7},
        {"rmse": 0.813, "mae": 0.621, "precision_at_10": 0.43},
    ),
]

_MODELS = [
    ModelArtifact(
        name="movie_recommender",
        version="1.0.0",
        stage=ModelStage.PRODUCTION,
        artifact_path="",
        parameters={
            "algorithm": "hybrid",
            "n_factors": 50,
            "content_weight": 0.3,
            "framework": "sklearn",
        },
    ),
    ModelArtifact(
        name="genre_classifier",
        version="1.0.0",
        stage=ModelStage.STAGING,
        artifact_path="",
        parameters={"algorithm": "random_forest", "n_estimators": 100, "framework": "sklearn"},
    ),
    ModelArtifact(
        name="rating_predictor",
        version="1.0.0",
        stage=ModelStage.DEVELOPMENT,
        artifact_path="",
        parameters={"algorithm": "SVD", "n_factors": 50, "framework": "sklearn"},
    ),
]


def _run_pipelines(eng: DexEngine) -> None:
    for name in _PIPELINES:
        try:
            print(f"  running pipeline: {name}")
            eng.run_pipeline(name)
        except Exception as exc:
            print(f"  [warn] {name}: {exc}")
    try:
        print("  running quality checks…")
        result = eng.quality_check_all_tables()
        score = result.get("overall_score", 0)
        print(f"  quality: score={score:.0%}  checks={result.get('total_checks', 0)}")
    except Exception as exc:
        print(f"  [warn] quality checks: {exc}")


def _seed_experiments(eng: DexEngine) -> None:
    tracker = eng.tracker
    if tracker is None:
        print("  [skip] no tracker configured")
        return
    exp_id = tracker.create_experiment("recommendation_model")
    for run_name, params, metrics in _EXPERIMENT_RUNS:
        run_id = tracker.start_run(exp_id, run_name=run_name)
        tracker.log_params(run_id, params)
        tracker.log_metrics(run_id, metrics)
        tracker.end_run(run_id, status="FINISHED")
        print(f"  logged run: {run_name}  rmse={metrics['rmse']}")
    genre_exp = tracker.create_experiment("genre_quality")
    for i, (split, rmse) in enumerate([("train", 0.791), ("val", 0.813), ("test", 0.829)]):
        run_id = tracker.start_run(genre_exp, run_name=f"eval_{split}")
        tracker.log_params(run_id, {"split": split, "n_genres": 19})
        tracker.log_metrics(run_id, {"rmse": rmse, "coverage": 0.92 - i * 0.02})
        tracker.end_run(run_id, status="FINISHED")


def _seed_models(eng: DexEngine) -> None:
    artifacts_dir = CONFIG.parent / ".dex" / "models"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    registry = eng.model_registry
    existing = registry.list_models()
    for artifact in _MODELS:
        artifact.artifact_path = str(artifacts_dir / f"{artifact.name}_v1.pkl")
        if artifact.name in existing:
            print(f"  [skip] model already registered: {artifact.name}")
        else:
            registry.register(artifact)
            print(
                f"  registered model: {artifact.name} v{artifact.version} ({artifact.stage.value})"
            )


def main() -> None:
    print("Initialising MovieDEX engine…")
    eng = DexEngine(CONFIG)
    _run_pipelines(eng)
    _seed_experiments(eng)
    _seed_models(eng)
    print("\nMovieDEX seed complete.")
    eng.store.close()


if __name__ == "__main__":
    main()
