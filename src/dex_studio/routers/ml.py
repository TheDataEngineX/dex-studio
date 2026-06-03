"""ML domain routes — models, experiments, predictions, features, drift."""

from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import (
    base_ctx,
    flash,
    get_eng,
    guard,
    render,
    stub_page,
)
from dex_studio.utils import fmt_ts

router = APIRouter()

_STAGES = ["development", "staging", "production"]


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ml_dashboard(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    models = eng.model_registry.list_models()
    exps: list[Any] = []
    if eng.tracker:
        with contextlib.suppress(Exception):
            exps = eng.tracker.list_experiments() or []
    ctx = base_ctx(request) | {
        "model_count": len(models),
        "experiment_count": len(exps),
        "feature_group_count": 0,
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
async def models(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    flash_msg = request.session.pop("flash", None)
    ctx = base_ctx(request) | {"models": _model_rows(eng), "stages": _STAGES, "flash": flash_msg}
    return render(request, "ml/models.html", ctx)


@router.post("/models/register")
async def register_model(
    request: Request,
    name: Annotated[str, Form()],
    version: Annotated[str, Form()] = "1.0.0",
    framework: Annotated[str, Form()] = "",
    artifact_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        from dataenginex.ml.registry import ModelArtifact, ModelStage

        eng = get_eng()
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
async def promote_model(
    request: Request,
    name: str,
    stage: Annotated[str, Form()],
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    try:
        from dataenginex.ml.registry import ModelStage

        eng = get_eng()
        latest = eng.model_registry.get_latest(name)
        if latest:
            eng.model_registry.promote(name, latest.version, ModelStage(stage))
            flash(request, f"'{name}' promoted to {stage}.")
    except Exception as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/ml/models", status_code=303)


@router.post("/models/delete/{name}")
async def delete_model(request: Request, name: str) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    get_eng().delete_model(name)
    flash(request, f"Model '{name}' deleted.")
    return RedirectResponse("/ml/models", status_code=303)


# ── Experiments ───────────────────────────────────────────────────────────────


@router.get("/experiments", response_class=HTMLResponse)
async def experiments(request: Request, exp: str = "") -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
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


# ── Predictions ───────────────────────────────────────────────────────────────


@router.get("/predictions", response_class=HTMLResponse)
async def predictions(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    model_names = eng.model_registry.list_models()
    ctx = base_ctx(request) | {
        "model_names": model_names,
        "output": "",
        "error": "",
        "input_json": "{}",
    }
    return render(request, "ml/predictions.html", ctx)


@router.post("/predictions/run", response_class=HTMLResponse)
async def run_prediction(
    request: Request,
    model: Annotated[str, Form()],
    input_json: Annotated[str, Form()],
) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    output = ""
    error = ""
    try:
        features = json.loads(input_json)
        if eng.serving_engine is None:
            error = "Serving engine not available."
        else:
            result = eng.serving_engine.predict(model, features)
            output = json.dumps(result, indent=2, default=str)
    except json.JSONDecodeError as exc:
        error = f"Invalid JSON: {exc}"
    except FileNotFoundError:
        error = (
            f"Model artifact not found for '{model}'. "
            "Train and save the model first, or register a valid artifact path."
        )
    except Exception as exc:
        error = str(exc)
    ctx = base_ctx(request) | {
        "model_names": eng.model_registry.list_models(),
        "selected_model": model,
        "output": output,
        "error": error,
        "input_json": input_json,
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


def _feature_group_detail(fs: Any, name: str) -> dict[str, str]:
    entity = ""
    row_count = ""
    with contextlib.suppress(Exception):
        row = fs._conn.execute(  # type: ignore[union-attr]
            "SELECT entity_key FROM _feature_groups WHERE name = ?", [name]
        ).fetchone()
        if row:
            entity = str(row[0])
    with contextlib.suppress(Exception):
        safe = name.replace('"', '""')
        row2 = fs._conn.execute(  # type: ignore[union-attr]
            f'SELECT COUNT(*) FROM "{safe}"'  # noqa: S608
        ).fetchone()
        if row2:
            row_count = f"{row2[0]:,}"
    return {"name": name, "entity": entity, "row_count": row_count}


@router.get("/features", response_class=HTMLResponse)
async def features(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    groups: list[dict[str, str]] = []
    if eng.feature_store is not None:
        with contextlib.suppress(Exception):
            for name in _feature_group_names(eng.feature_store):
                groups.append(_feature_group_detail(eng.feature_store, name))
    ctx = base_ctx(request) | {"feature_groups": groups}
    return render(request, "ml/features.html", ctx)


# ── Drift ─────────────────────────────────────────────────────────────────────


@router.get("/drift", response_class=HTMLResponse)
async def drift(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
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
async def run_drift(  # noqa: C901
    request: Request,
    table: Annotated[str, Form()] = "",
    feature: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
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
async def ml_stub(request: Request) -> HTMLResponse:
    if redir := guard(request):
        return redir  # type: ignore[return-value]
    return stub_page(request, _ML_STUB_TITLES)
