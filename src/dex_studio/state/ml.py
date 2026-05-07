"""Reflex state for ML features — experiments, models, predictions, features, drift."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx

from dex_studio.state.base import BaseState


class MLState(BaseState):
    """State for ML pages: experiment tracking, model registry, serving, feature store, drift."""

    experiments: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    selected_experiment: str = ""
    feature_groups: list[dict[str, Any]] = []
    drift_data: dict[str, Any] = {}
    drift_features: list[dict[str, Any]] = []
    drift_score: str = "—"
    predict_input: str = "{}"
    predict_output: str = ""

    @rx.event
    async def load_experiments(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            if eng.tracker is None:
                self.experiments = []
            else:
                raw = eng.tracker.list_experiments()
                enriched = []
                for e in raw:
                    exp_id = e.get("id") or e.get("experiment_id", "")
                    runs = eng.tracker.list_runs(exp_id)
                    enriched.append(
                        {
                            **e,
                            "run_count": len(runs),
                            "created_at": (runs[0].get("started_at", "-")[:10] if runs else "-"),
                        }
                    )
                self.experiments = enriched
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def select_experiment(self, name: str) -> AsyncGenerator[None]:
        self.selected_experiment = name
        self.is_loading = True
        yield
        try:
            eng = self._engine()
            if eng.tracker is not None:
                exps = eng.tracker.list_experiments()
                exp_id = next(
                    (
                        e.get("id") or e.get("experiment_id", "")
                        for e in exps
                        if e.get("name") == name
                    ),
                    name,
                )
                raw_runs = eng.tracker.list_runs(exp_id)
                self.runs = [
                    {
                        **r,
                        "primary_metric": next(
                            (
                                f"{k}={list(v)[-1]['value']:.4f}"
                                for k, v in r.get("metrics", {}).items()
                            ),
                            "-",
                        ),
                    }
                    for r in raw_runs
                ]
            else:
                self.runs = []
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_models(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            names = eng.model_registry.list_models()
            rows = []
            for n in names:
                latest = eng.model_registry.get_latest(n)
                rows.append(
                    {
                        "name": n,
                        "version": latest.version if latest else "-",
                        "stage": latest.stage.value if latest else "-",
                        "framework": getattr(latest, "framework", "-") if latest else "-",
                    }
                )
            self.models = rows
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def promote_model(self, name: str, stage: str) -> AsyncGenerator[None]:
        self.is_loading = True
        yield
        try:
            from dataenginex.ml.registry import ModelStage

            eng = self._engine()
            latest = eng.model_registry.get_latest(name)
            if latest is None:
                self._set_error(f"No version found for model '{name}'")
            else:
                eng.model_registry.promote(name, latest.version, ModelStage(stage))
                self._push_toast(f"Model '{name}' promoted to {stage}", "success")
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False
        async for _ in self.load_models():  # type: ignore[attr-defined]
            yield

    @rx.event
    async def load_features(self) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            if eng.feature_store is not None and hasattr(eng.feature_store, "list_groups"):
                self.feature_groups = eng.feature_store.list_groups()
            else:
                self.feature_groups = []
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def check_drift(self, pipeline: str) -> AsyncGenerator[None]:
        self.is_loading = True
        self.error = ""
        yield
        try:
            eng = self._engine()
            data: dict[str, Any] = {}
            if eng.tracker is not None and hasattr(eng.tracker, "check_drift"):
                data = eng.tracker.check_drift(pipeline)
            self.drift_data = data
            self.drift_features = data.get("features", [])
            self.drift_score = str(data.get("score", "—"))
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    async def load_drift(self) -> AsyncGenerator[None]:
        async for _ in self.check_drift("default"):  # type: ignore[attr-defined]
            yield

    @rx.event
    async def run_prediction(self, model: str) -> AsyncGenerator[None]:
        self.is_loading = True
        self.predict_output = ""
        self.error = ""
        yield
        try:
            features = json.loads(self.predict_input)
        except json.JSONDecodeError as exc:
            self.error = f"Invalid JSON: {exc}"
            self.is_loading = False
            return
        try:
            eng = self._engine()
            if eng.serving_engine is None:
                self._set_error("Serving engine not available")
            else:
                result = eng.serving_engine.predict(model, features)
                self.predict_output = json.dumps(result, indent=2, default=str)
        except Exception as exc:
            self._set_error(str(exc))
        finally:
            self.is_loading = False

    @rx.event
    def set_predict_input(self, v: str) -> None:
        self.predict_input = v
