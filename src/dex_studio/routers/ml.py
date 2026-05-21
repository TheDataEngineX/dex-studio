"""ML domain routes — models, experiments, predictions, features, drift."""

from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dex_studio.routers._deps import base_ctx, get_eng, render, require_auth, require_engine
from dex_studio.utils import fmt_ts

router = APIRouter()

_STAGES = ["development", "staging", "production"]


def _guard(request: Request) -> RedirectResponse | None:
    return require_auth(request) or require_engine(request)


# ── Dashboard ─────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ml_dashboard(request: Request) -> HTMLResponse:
    if redir := _guard(request):
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
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    flash = request.session.pop("flash", None)
    ctx = base_ctx(request) | {"models": _model_rows(eng), "stages": _STAGES, "flash": flash}
    return render(request, "ml/models.html", ctx)


@router.post("/models/register")
async def register_model(
    request: Request,
    name: Annotated[str, Form()],
    version: Annotated[str, Form()] = "1.0.0",
    framework: Annotated[str, Form()] = "",
    artifact_path: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if redir := _guard(request):
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
        request.session["flash"] = {"msg": f"Model '{name}' registered.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/ml/models", status_code=303)


@router.post("/models/promote/{name}")
async def promote_model(
    request: Request,
    name: str,
    stage: Annotated[str, Form()],
) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    try:
        from dataenginex.ml.registry import ModelStage

        eng = get_eng()
        latest = eng.model_registry.get_latest(name)
        if latest:
            eng.model_registry.promote(name, latest.version, ModelStage(stage))
            request.session["flash"] = {"msg": f"'{name}' promoted to {stage}.", "kind": "success"}
    except Exception as exc:
        request.session["flash"] = {"msg": str(exc), "kind": "error"}
    return RedirectResponse("/ml/models", status_code=303)


@router.post("/models/delete/{name}")
async def delete_model(request: Request, name: str) -> RedirectResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    get_eng().delete_model(name)
    request.session["flash"] = {"msg": f"Model '{name}' deleted.", "kind": "success"}
    return RedirectResponse("/ml/models", status_code=303)


# ── Experiments ───────────────────────────────────────────────────────────────


@router.get("/experiments", response_class=HTMLResponse)
async def experiments(request: Request, exp: str = "") -> HTMLResponse:
    if redir := _guard(request):
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
    if redir := _guard(request):
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
    if redir := _guard(request):
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


@router.get("/features", response_class=HTMLResponse)
async def features(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    groups: list[dict[str, str]] = []
    if eng.feature_store and hasattr(eng.feature_store, "list_groups"):
        try:
            raw = eng.feature_store.list_groups() or []
            for g in raw:
                groups.append(
                    {
                        "name": str(g.get("name", "") if isinstance(g, dict) else g),
                        "entity": str(g.get("entity", "") if isinstance(g, dict) else ""),
                        "feature_count": str(
                            g.get("feature_count", "") if isinstance(g, dict) else ""
                        ),
                    }
                )
        except Exception:
            pass
    ctx = base_ctx(request) | {"feature_groups": groups}
    return render(request, "ml/features.html", ctx)


# ── Drift ─────────────────────────────────────────────────────────────────────


@router.get("/drift", response_class=HTMLResponse)
async def drift(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    eng = get_eng()
    data: dict[str, Any] = {}
    features_list: list[dict[str, str]] = []
    drift_score = "—"
    if eng.tracker and hasattr(eng.tracker, "check_drift"):
        try:
            data = eng.tracker.check_drift("default") or {}
            features_list = [
                {
                    "name": str(f.get("name", f.get("feature", ""))),
                    "psi": str(f.get("psi", "—")),
                    "status": str(f.get("status", "ok")),
                }
                for f in data.get("features", [])
            ]
            drift_score = str(data.get("score", "—"))
        except Exception:
            pass
    ctx = base_ctx(request) | {
        "drift_score": drift_score,
        "drift_features": features_list,
    }
    return render(request, "ml/drift.html", ctx)


# ── Stubs ─────────────────────────────────────────────────────────────────────


@router.get("/hyperopt", response_class=HTMLResponse)
@router.get("/ab-test", response_class=HTMLResponse)
@router.get("/model-card", response_class=HTMLResponse)
@router.get("/promotions", response_class=HTMLResponse)
async def ml_stub(request: Request) -> HTMLResponse:
    if redir := _guard(request):
        return redir  # type: ignore[return-value]
    titles = {
        "/ml/hyperopt": "Hyperparameter Optimization",
        "/ml/ab-test": "A/B Testing",
        "/ml/model-card": "Model Cards",
        "/ml/promotions": "Promotion Workflow",
    }
    ctx = base_ctx(request) | {"page_title": titles.get(request.url.path, "Coming Soon")}
    return render(request, "stub.html", ctx)
