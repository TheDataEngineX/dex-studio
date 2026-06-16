"""ML domain routes — models, experiments, predictions, features, drift."""

from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio import _json
from dex_studio.routers._deps import (
    ReadDep,
    WriteDep,
    base_ctx,
    flash,
    render,
    stub_page,
)
from dex_studio.utils import fmt_ts

router = APIRouter()

_STAGES = ["development", "staging", "production"]


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def ml_dashboard(request: Request, eng: ReadDep) -> HTMLResponse:
    models = eng.model_registry.list_models()
    exps: list[Any] = []
    if eng.tracker:
        with contextlib.suppress(Exception):
            exps = eng.tracker.list_experiments() or []
    feature_group_count = 0
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            feature_group_count = len(_feature_group_names(eng.feature_store))
    ctx = base_ctx(request) | {
        "model_count": len(models),
        "experiment_count": len(exps),
        "feature_group_count": feature_group_count,
    }
    return render(request, "ml/dashboard.html", ctx)


# ── Models ────────────────────────────────────────────────────────────────────


def _model_rows(eng: Any) -> list[dict[str, str]]:
    rows = []
    for name in eng.model_registry.list_models():
        latest = eng.model_registry.get_latest(name)
        rows.append(
            {
                "name": name,
                "version": str(latest.version) if latest else "—",
                "stage": str(latest.stage.value) if latest else "—",
                "framework": str(latest.parameters.get("framework", "—")) if latest else "—",
            }
        )
    return rows


@router.get("/models", response_class=HTMLResponse)
def models(request: Request, eng: ReadDep) -> HTMLResponse:
    ctx = base_ctx(request) | {"models": _model_rows(eng), "stages": _STAGES}
    return render(request, "ml/models.html", ctx)


@router.post("/models/register")
def register_model(
    request: Request,
    eng: WriteDep,
    name: Annotated[str, Form()],
    version: Annotated[str, Form()] = "1.0.0",
    framework: Annotated[str, Form()] = "",
    artifact_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        from dataenginex.ml.registry import ModelArtifact, ModelStage

        artifact = ModelArtifact(
            name=name.strip(),
            version=version.strip() or "1.0.0",
            stage=ModelStage.DEVELOPMENT,
            artifact_path=artifact_path.strip(),
            parameters={"framework": framework.strip()} if framework.strip() else {},
        )
        eng.model_registry.register(artifact)
        flash(request, f"Model '{name}' registered.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ml/models", status_code=303)


@router.post("/models/promote/{name}")
def promote_model(
    request: Request,
    eng: WriteDep,
    name: str,
    stage: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        from dataenginex.ml.registry import ModelStage

        latest = eng.model_registry.get_latest(name)
        if latest:
            eng.model_registry.promote(name, latest.version, ModelStage(stage))
            flash(request, f"'{name}' promoted to {stage}.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ml/models", status_code=303)


@router.post("/models/delete/{name}")
def delete_model(request: Request, eng: WriteDep, name: str) -> RedirectResponse:
    eng.delete_model(name)
    flash(request, f"Model '{name}' deleted.")
    return RedirectResponse("/ml/models", status_code=303)


# ── Experiments ───────────────────────────────────────────────────────────────


@router.get("/experiments", response_class=HTMLResponse)
def experiments(request: Request, eng: ReadDep, exp: str = "") -> HTMLResponse:
    exp_list: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if eng.tracker:
        try:
            raw = eng.tracker.list_experiments() or []
            for e in raw:
                exp_id = e.get("id") or e.get("experiment_id", "")
                exp_runs = eng.tracker.list_runs(exp_id)
                exp_list.append(
                    {
                        "name": str(e.get("name", "")),
                        "run_count": len(exp_runs),
                        "created_at": exp_runs[0].get("started_at", "—")[:10] if exp_runs else "—",
                    }
                )
            if exp:
                exp_id = next(
                    (
                        e.get("id") or e.get("experiment_id", "")
                        for e in raw
                        if e.get("name") == exp
                    ),
                    exp,
                )
                for r in eng.tracker.list_runs(exp_id):
                    metric_str = next(
                        (
                            f"{k}={list(v)[-1]['value']:.4f}"
                            for k, v in r.get("metrics", {}).items()
                        ),
                        "—",
                    )
                    runs.append(
                        {
                            "run_id": str(r.get("run_id", r.get("id", ""))),
                            "status": str(r.get("status", "")),
                            "primary_metric": metric_str,
                            "started_at": fmt_ts(r.get("started_at", "")),
                        }
                    )
        except Exception:
            pass
    ctx = base_ctx(request) | {
        "experiments": exp_list,
        "selected_exp": exp,
        "runs": runs,
    }
    return render(request, "ml/experiments.html", ctx)


@router.post("/experiments/new")
def new_experiment(
    request: Request,
    eng: WriteDep,
    exp_name: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        name = exp_name.strip()
        if not name:
            flash(request, "Experiment name is required.", "error")
            return RedirectResponse("/ml/experiments", status_code=303)
        if eng.tracker:
            eng.tracker.create_experiment(name)
            flash(request, f"Experiment '{name}' created.")
        else:
            flash(request, "Tracker not available — check engine config.", "error")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ml/experiments", status_code=303)


# ── Predictions ───────────────────────────────────────────────────────────────


def _feature_default(name: str) -> float:
    """A sensible non-zero default per feature so the example prediction is meaningful."""
    n = name.lower()
    if "rating" in n:
        return 7.0
    if "count" in n:
        return 10.0
    if n.startswith("g_"):
        return 0.0
    if "norm" in n:
        return 0.5
    return 0.0


def _prediction_meta(eng: Any, model_names: list[str]) -> dict[str, dict[str, Any]]:
    """Per-model metadata for the predictions form: purpose, feature names, defaults."""
    meta: dict[str, dict[str, Any]] = {}
    for name in model_names:
        with contextlib.suppress(Exception):
            art = eng.model_registry.get_latest(name)
            params = getattr(art, "parameters", {}) or {}
            feats = [str(f) for f in (params.get("feature_names") or [])]
            meta[name] = {
                "description": str(getattr(art, "description", "") or ""),
                "features": feats,
                "defaults": {f: _feature_default(f) for f in feats},
            }
    return meta


@router.get("/predictions", response_class=HTMLResponse)
def predictions(request: Request, eng: ReadDep) -> HTMLResponse:
    model_names = eng.model_registry.list_models()
    meta = _prediction_meta(eng, model_names)
    default_model = model_names[0] if model_names else ""
    out_meta = _output_meta(default_model)
    ctx = base_ctx(request) | {
        "model_names": model_names,
        "selected_model": default_model,
        "model_meta_json": _json.dumps(meta),
        "prediction": None,
        "model_desc": "",
        "prediction_label": out_meta["label"],
        "prediction_unit": out_meta["unit"],
        "prediction_context": out_meta["context"],
        "output": "",
        "error": "",
    }
    return render(request, "ml/predictions.html", ctx)


def _parse_prediction(output: str) -> float | None:
    """Pull the first numeric prediction out of the serving engine's JSON output."""
    with contextlib.suppress(Exception):
        parsed = _json.loads(output)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], int | float):
            return round(float(parsed[0]), 3)
    return None


_MODEL_OUTPUT_META: dict[str, dict[str, str]] = {
    "rating_predictor": {
        "label": "Predicted IMDB rating",
        "unit": "/ 10",
        "context": (
            "Higher = better rated. 7+ is well-received; 8+ is acclaimed. "
            "Based on structural features like runtime, vote count, and director history."
        ),
    },
    "movie_recommender": {
        "label": "Recommendation score",
        "unit": "/ 10",
        "context": (
            "This is a content-quality score, not a movie name. "
            "Higher = stronger match based on genre mix and director signals. "
            "Use the AI Playground → movie_recommender agent to get actual movie titles."
        ),
    },
    "genre_classifier": {
        "label": "Predicted decade",
        "unit": "s",
        "context": (
            "The model predicts which decade the movie is from based on genre and rating. "
            "e.g. 1990 → 1990s, 2010 → 2010s."
        ),
    },
}


def _output_meta(model: str) -> dict[str, str]:
    """Return display metadata for the model's output value."""
    return _MODEL_OUTPUT_META.get(model, {"label": "Predicted value", "unit": "", "context": ""})


@router.post("/predictions/run", response_class=HTMLResponse)
def run_prediction(
    request: Request,
    eng: WriteDep,
    model: Annotated[str, Form()],
    input_json: Annotated[str, Form()],
) -> HTMLResponse:
    output = ""
    error = ""
    try:
        features = _json.loads(input_json)
        if eng.serving_engine is None:
            error = "Serving engine not available."
        else:
            result = eng.serving_engine.predict(model, features)
            output = _json.dumps(result, indent=2, default=str)
    except ValueError as exc:
        error = f"Invalid JSON: {exc}"
    except FileNotFoundError:
        error = (
            f"Model artifact not found for '{model}'. "
            "Train and save the model first, or register a valid artifact path."
        )
    except Exception as exc:
        error = str(exc)
    prediction = _parse_prediction(output) if (not error and output) else None
    model_desc = ""
    with contextlib.suppress(Exception):
        art = eng.model_registry.get_latest(model)
        model_desc = str(getattr(art, "description", "") or "")
    out_meta = _output_meta(model)
    ctx = base_ctx(request) | {
        "model_names": eng.model_registry.list_models(),
        "selected_model": model,
        "model_meta_json": _json.dumps(_prediction_meta(eng, eng.model_registry.list_models())),
        "prediction": prediction,
        "model_desc": model_desc,
        "prediction_label": out_meta["label"],
        "prediction_unit": out_meta["unit"],
        "prediction_context": out_meta["context"],
        "output": output,
        "error": error,
    }
    if request.headers.get("HX-Request"):
        return render(request, "ml/prediction_result.html", ctx)
    return render(request, "ml/predictions.html", ctx)


# ── Features ──────────────────────────────────────────────────────────────────


def _feature_group_names(fs: Any) -> list[str]:
    if hasattr(fs, "list_feature_groups"):
        return fs.list_feature_groups() or []
    if hasattr(fs, "list_groups"):
        raw = fs.list_groups() or []
        return [g if isinstance(g, str) else str(g.get("name", g)) for g in raw]
    return []


@router.get("/features", response_class=HTMLResponse)
def features(request: Request, eng: ReadDep) -> HTMLResponse:
    groups: list[dict[str, str]] = []
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            groups = eng.feature_store.feature_group_info()
    ctx = base_ctx(request) | {"feature_groups": groups}
    return render(request, "ml/features.html", ctx)


# ── Drift ─────────────────────────────────────────────────────────────────────


@router.get("/drift", response_class=HTMLResponse)
def drift(request: Request, eng: ReadDep) -> HTMLResponse:
    features_list: list[dict[str, str]] = []
    drift_score = "—"
    silver = eng.project_dir / ".dex" / "lakehouse" / "silver"
    silver_tables = [p.stem for p in sorted(silver.glob("*.parquet"))] if silver.exists() else []
    drift_result = request.session.pop("drift_result", None)
    drift_error = request.session.pop("drift_error", None)
    if drift_result:
        features_list = [
            {
                "name": drift_result["feature"],
                "psi": str(drift_result["psi"]),
                "status": "warning" if drift_result["drift_detected"] else "ok",
            }
        ]
        drift_score = str(drift_result["psi"])
    ctx = base_ctx(request) | {
        "drift_score": drift_score,
        "drift_features": features_list,
        "silver_tables": silver_tables,
        "drift_result": drift_result,
        "drift_error": drift_error,
    }
    return render(request, "ml/drift.html", ctx)


_DRIFT_URL = "/ml/drift"


@router.post("/drift/run")
def run_drift(  # noqa: C901
    request: Request,
    eng: WriteDep,
    table: Annotated[str, Form()] = "",
    feature: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        import duckdb
        from dataenginex.ml.drift import DriftDetector

        dex_dir = eng.project_dir / ".dex"
        if not table:
            silver = dex_dir / "lakehouse" / "silver"
            parquets = sorted(silver.glob("*.parquet")) if silver.exists() else []
            if parquets:
                table = parquets[0].stem
        parquet_path = dex_dir / "lakehouse" / "silver" / f"{table}.parquet"
        if not parquet_path.exists():
            request.session["drift_error"] = f"Table '{table}' not found in silver layer."
            return RedirectResponse(_DRIFT_URL, status_code=303)

        abs_path = str(parquet_path.resolve())
        with duckdb.connect(":memory:") as conn:
            row = conn.execute("SELECT COUNT(*) FROM read_parquet($1)", [abs_path]).fetchone()
            total = row[0] if row else 0
            if total < 10:
                request.session["drift_error"] = "Not enough rows for drift detection."
                return RedirectResponse(_DRIFT_URL, status_code=303)
            mid = total // 2
            if not feature:
                cols = conn.execute(
                    "DESCRIBE SELECT * FROM read_parquet($1) LIMIT 1", [abs_path]
                ).fetchall()
                numeric = [c[0] for c in cols if c[1] in ("DOUBLE", "FLOAT", "BIGINT", "INTEGER")]
                feature = numeric[0] if numeric else ""
            if not feature:
                request.session["drift_error"] = "No numeric feature found."
                return RedirectResponse(_DRIFT_URL, status_code=303)
            safe_col = feature.replace('"', '""')
            ref_rows = conn.execute(
                f'SELECT "{safe_col}" FROM read_parquet($1) LIMIT {mid}', [abs_path]
            ).fetchall()
            cur_rows = conn.execute(
                f'SELECT "{safe_col}" FROM read_parquet($1) LIMIT {total - mid} OFFSET {mid}',
                [abs_path],
            ).fetchall()
        reference = [float(r[0]) for r in ref_rows if r[0] is not None]
        current = [float(r[0]) for r in cur_rows if r[0] is not None]
        detector = DriftDetector(psi_threshold=eng.config.ml.drift.threshold)
        report = detector.check_feature(feature, reference, current)
        request.session["drift_result"] = {
            "table": table,
            "feature": feature,
            "psi": round(report.psi, 4),
            "drift_detected": report.drift_detected,
            "severity": report.severity,
        }
    except Exception as exc:
        request.session["drift_error"] = str(exc)
    return RedirectResponse(_DRIFT_URL, status_code=303)


# ── Stubs ─────────────────────────────────────────────────────────────────────

_ML_STUB_TITLES = {
    "/ml/hyperopt": "Hyperparameter Optimization",
    "/ml/ab-test": "A/B Testing",
    "/ml/model-card": "Model Cards",
    "/ml/promotions": "Promotion Workflow",
}


@router.get("/hyperopt", response_class=HTMLResponse)
@router.get("/ab-test", response_class=HTMLResponse)
@router.get("/model-card", response_class=HTMLResponse)
@router.get("/promotions", response_class=HTMLResponse)
def ml_stub(request: Request, _: ReadDep) -> HTMLResponse:
    return stub_page(request, _ML_STUB_TITLES)
