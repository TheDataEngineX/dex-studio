"""
Train and register all three movie-dex ML models with the current sklearn version.
Run from dex-studio root: uv run python examples/movie-dex/train_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from dataenginex.ml.registry import ModelArtifact, ModelRegistry, ModelStage  # noqa: E402
from dataenginex.ml.training import SklearnTrainer  # noqa: E402
from sklearn.ensemble import (  # noqa: E402
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)

DEX_DIR = Path(__file__).parent / ".dex"
MODEL_DIR = DEX_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_PATH = MODEL_DIR / "registry.json"
FEATURES_PKL = DEX_DIR / "lakehouse" / "gold" / "gold_movie_features.parquet"

# Feature columns in exact order — prediction input dicts must use the same order
RATING_FEATURES = [
    "year_norm",
    "runtime_norm",
    "log_votes_norm",
    "director_avg_rating",
    "director_filmcount",
    "g_action",
    "g_drama",
    "g_comedy",
    "g_thriller",
    "g_crime",
    "g_romance",
    "g_scifi",
    "g_horror",
    "g_adventure",
    "g_animation",
    "g_biography",
    "g_documentary",
    "g_fantasy",
    "g_mystery",
]

RECOMMENDER_FEATURES = [
    "g_action",
    "g_drama",
    "g_comedy",
    "g_thriller",
    "g_crime",
    "g_romance",
    "g_scifi",
    "g_horror",
    "g_adventure",
    "g_animation",
    "g_fantasy",
    "g_mystery",
    "year_norm",
    "director_avg_rating",
]

CLASSIFIER_FEATURES = [
    "imdb_rating",
    "log_votes_norm",
    "g_action",
    "g_drama",
    "g_comedy",
    "g_thriller",
    "g_scifi",
    "g_horror",
    "g_romance",
    "g_animation",
]


def load_features() -> pd.DataFrame:
    if not FEATURES_PKL.exists():
        raise FileNotFoundError(f"{FEATURES_PKL} not found. Run the pipeline first in DEX Studio.")
    df = pd.read_parquet(FEATURES_PKL)
    print(f"  loaded {len(df):,} rows  columns: {list(df.columns)}")
    return df


def _prep(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = 0.0
    return df[cols].fillna(0.0)


def _subsample(
    X: np.ndarray, y: np.ndarray, n: int = 50_000, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    if len(X) > n:
        idx = np.random.default_rng(seed).choice(len(X), n, replace=False)
        return X[idx], y[idx]
    return X, y


def train_rating_predictor(df: pd.DataFrame, registry: ModelRegistry) -> None:
    print("\n[1/3] rating_predictor …")
    target = "target_rating" if "target_rating" in df.columns else "imdb_rating"
    mask = df[target].notna()
    X, y = _subsample(
        _prep(df[mask].copy(), RATING_FEATURES).values,
        df.loc[mask, target].values,
    )
    trainer = SklearnTrainer(
        "rating_predictor",
        "1.0.0",
        estimator=RandomForestRegressor(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=20,
            random_state=42,
            n_jobs=-1,
        ),
    )
    result = trainer.train(X, y)
    print(f"  train_score={result.metrics['train_score']:.4f}")
    artifact = str(MODEL_DIR / "rating_predictor_v1.pkl")
    trainer.save(artifact)
    registry.register(
        ModelArtifact(
            name="rating_predictor",
            version="1.0.0",
            artifact_path=artifact,
            metrics=result.metrics,
            parameters={
                "algorithm": "random_forest",
                "n_estimators": 150,
                "framework": "sklearn",
                "feature_names": RATING_FEATURES,
            },
            stage=ModelStage.PRODUCTION,
            description="Predicts IMDB rating from structural movie features.",
        )
    )
    print(f"  saved  {artifact}")


def train_movie_recommender(df: pd.DataFrame, registry: ModelRegistry) -> None:
    print("\n[2/3] movie_recommender …")
    target = "target_rating" if "target_rating" in df.columns else "imdb_rating"
    mask = df[target].notna()
    X, y = _subsample(
        _prep(df[mask].copy(), RECOMMENDER_FEATURES).values,
        df.loc[mask, target].values,
        seed=7,
    )
    trainer = SklearnTrainer(
        "movie_recommender",
        "1.0.0",
        estimator=GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        ),
    )
    result = trainer.train(X, y)
    print(f"  train_score={result.metrics['train_score']:.4f}")
    artifact = str(MODEL_DIR / "movie_recommender_v1.pkl")
    trainer.save(artifact)
    registry.register(
        ModelArtifact(
            name="movie_recommender",
            version="1.0.0",
            artifact_path=artifact,
            metrics=result.metrics,
            parameters={
                "algorithm": "gradient_boosting",
                "n_estimators": 100,
                "framework": "sklearn",
                "feature_names": RECOMMENDER_FEATURES,
            },
            stage=ModelStage.PRODUCTION,
            description="Content-based recommendation score from genre and director features.",
        )
    )
    print(f"  saved  {artifact}")


def train_genre_classifier(df: pd.DataFrame, registry: ModelRegistry) -> None:
    print("\n[3/3] genre_classifier …")
    if "decade" not in df.columns:
        print("  SKIP — 'decade' column missing")
        return
    d = df[df["decade"].notna() & (df["decade"] > 0)].copy()
    if "imdb_rating" not in d.columns and "target_rating" in d.columns:
        d = d.rename(columns={"target_rating": "imdb_rating"})
    X, y = _subsample(
        _prep(d, CLASSIFIER_FEATURES).values,
        d["decade"].astype(int).values,
        seed=13,
    )
    trainer = SklearnTrainer(
        "genre_classifier",
        "1.0.0",
        estimator=RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            random_state=42,
            n_jobs=-1,
        ),
    )
    result = trainer.train(X, y)
    print(f"  train_score={result.metrics['train_score']:.4f}")
    artifact = str(MODEL_DIR / "genre_classifier_v1.pkl")
    trainer.save(artifact)
    registry.register(
        ModelArtifact(
            name="genre_classifier",
            version="1.0.0",
            artifact_path=artifact,
            metrics=result.metrics,
            parameters={
                "algorithm": "random_forest",
                "n_estimators": 100,
                "framework": "sklearn",
                "feature_names": CLASSIFIER_FEATURES,
            },
            stage=ModelStage.STAGING,
            description="Classifies which decade a movie is from using genre and rating signals.",
        )
    )
    print(f"  saved  {artifact}")


if __name__ == "__main__":
    print("=== MovieDEX Model Training ===")
    df = load_features()
    registry = ModelRegistry(persist_path=str(REGISTRY_PATH))
    train_rating_predictor(df, registry)
    train_movie_recommender(df, registry)
    train_genre_classifier(df, registry)
    print("\n=== Done ===")
