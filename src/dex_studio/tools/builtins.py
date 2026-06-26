"""Platform built-in tools — Tier 1 of the three-tier registry.

These are always available regardless of project configuration.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dex_studio.tools.registry import ToolRegistry


def register_builtins(registry: ToolRegistry) -> None:
    """Register all platform built-in tools."""
    from dex_studio.tools.registry import ToolParam

    registry.register_builtin(
        "query",
        "Run a SQL query against the DuckDB lakehouse. Returns rows and column names.",
        _tool_query,
        [ToolParam("sql", "str", True, description="SQL query to execute")],
    )
    registry.register_builtin(
        "predict",
        "Run inference against a trained ML model from the model registry.",
        _tool_predict,
        [
            ToolParam("model", "str", True, description="Model name from registry"),
            ToolParam(
                "features", "dict", True, description="Feature dict matching the model's schema"
            ),
        ],
    )
    registry.register_builtin(
        "search_semantic",
        "Semantic similarity search over an embedding collection.",
        _tool_search_semantic,
        [
            ToolParam("query", "str", True, description="Natural-language query"),
            ToolParam("collection", "str", True, description="Embedding collection name"),
            ToolParam("n", "int", False, 10, "Number of results"),
        ],
    )
    registry.register_builtin(
        "profile_table",
        "Profile a lakehouse table: row count, null rates, top values per column.",
        _tool_profile_table,
        [ToolParam("table", "str", True, description="Table name (any layer)")],
    )
    registry.register_builtin(
        "list_tables",
        "List all available tables in the lakehouse, grouped by layer.",
        _tool_list_tables,
    )
    registry.register_builtin(
        "get_schema",
        "Return column names and types for a lakehouse table.",
        _tool_get_schema,
        [ToolParam("table", "str", True, description="Table name")],
    )
    registry.register_builtin(
        "run_pipeline",
        "Trigger a named pipeline run and return its status.",
        _tool_run_pipeline,
        [ToolParam("name", "str", True, description="Pipeline name from dex.yaml")],
    )
    registry.register_builtin(
        "detect_anomalies",
        "Detect statistical anomalies in a numeric column using Z-score.",
        _tool_detect_anomalies,
        [
            ToolParam("table", "str", True, description="Table name"),
            ToolParam("column", "str", True, description="Numeric column name"),
            ToolParam("threshold", "float", False, 3.0, "Z-score threshold (default 3.0)"),
        ],
    )
    registry.register_builtin(
        "finetune",
        "Train a new ML model on lakehouse data and register it for predict().",
        _tool_finetune,
        [
            ToolParam("feature_set", "str", True, description="Name of feature set or gold table"),
            ToolParam("target", "str", True, description="Target column to predict"),
            ToolParam("algorithm", "str", False, "random_forest", "sklearn estimator name"),
            ToolParam("model_name", "str", False, "", "Name to register model under"),
        ],
    )


# ── Tool implementations ───────────────────────────────────────────────────────


def _tool_query(sql: str) -> Any:
    try:
        from dataenginex.ai.tools import tool_registry as _dex  # type: ignore[import-untyped]

        return _dex.call("query", sql=sql)
    except Exception:
        pass
    import duckdb  # type: ignore[import-untyped]

    with duckdb.connect(":memory:") as conn:
        return conn.execute(sql).fetchdf()


def _tool_predict(model: str, features: dict[str, Any]) -> Any:
    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng is None:
        return {"error": "No engine available"}
    if eng.serving_engine is None:
        return {"error": "Serving engine not configured"}
    try:
        result = eng.serving_engine.predict(model, features)
        return {"prediction": result, "model": model}
    except FileNotFoundError:
        return {"error": f"Model '{model}' artifact not found — train it first"}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_search_semantic(query: str, collection: str, n: int = 10) -> Any:
    from dex_studio._engine import get_engine
    from dex_studio.embeddings import search_collection

    eng = get_engine()
    if eng is None:
        return {"error": "No engine available"}
    results = search_collection(eng, collection, query, top_k=n)
    return {"results": results, "collection": collection, "count": len(results)}


def _tool_profile_table(table: str) -> dict[str, Any]:
    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng is None:
        return {"error": "No engine available"}

    profile: dict[str, Any] = {"table": table, "columns": []}
    with contextlib.suppress(Exception):
        for layer in ("gold", "silver", "bronze"):
            schema = eng.warehouse_table_schema(table, layer)
            if schema:
                profile["layer"] = layer
                profile["columns"] = schema
                break

    try:
        result = _tool_query(f"SELECT COUNT(*) AS row_count FROM {table}")
        if hasattr(result, "to_dict"):
            profile["row_count"] = int(result["row_count"].iloc[0])
        elif isinstance(result, list) and result:
            profile["row_count"] = result[0].get("row_count", 0)
    except Exception:
        profile["row_count"] = "unknown"

    return profile


def _tool_list_tables() -> dict[str, list[str]]:
    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng is None:
        return {}
    result: dict[str, list[str]] = {}
    for layer in ("bronze", "silver", "gold"):
        with contextlib.suppress(Exception):
            result[layer] = [t["name"] for t in (eng.warehouse_tables(layer) or [])]
    return result


def _tool_get_schema(table: str) -> dict[str, Any]:
    from dex_studio._engine import get_engine

    eng = get_engine()
    if eng is None:
        return {"error": "No engine available"}
    for layer in ("gold", "silver", "bronze"):
        with contextlib.suppress(Exception):
            schema = eng.warehouse_table_schema(table, layer)
            if schema:
                return {"table": table, "layer": layer, "columns": schema}
    return {"error": f"Table '{table}' not found in any layer"}


def _tool_run_pipeline(name: str) -> dict[str, Any]:
    from dex_studio._engine import get_engine
    from dex_studio.jobs import run_pipeline_bg

    eng = get_engine()
    if eng is None:
        return {"error": "No engine available"}
    if name not in (eng.config.data.pipelines or {}):
        available = list((eng.config.data.pipelines or {}).keys())
        return {"error": f"Pipeline '{name}' not found. Available: {available}"}
    run_pipeline_bg(name)
    return {"status": "triggered", "pipeline": name}


def _tool_detect_anomalies(table: str, column: str, threshold: float = 3.0) -> Any:
    import contextlib as _ctx

    result: dict[str, Any] = {"table": table, "column": column, "anomalies": []}
    with _ctx.suppress(Exception):
        import duckdb  # type: ignore[import-untyped]

        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return {"error": "No engine"}
        safe_col = column.replace('"', '""')
        for layer in ("gold", "silver", "bronze"):
            parquet = eng.project_dir / ".dex" / "lakehouse" / layer / f"{table}.parquet"
            if not parquet.exists():
                continue
            with duckdb.connect(":memory:") as conn:
                stats = conn.execute(
                    f'SELECT AVG("{safe_col}") AS mean, STDDEV("{safe_col}") AS std '
                    f"FROM read_parquet($1)",
                    [str(parquet)],
                ).fetchone()
                if not stats or stats[1] is None or stats[1] == 0:
                    break
                mean, std = stats
                rows = conn.execute(
                    f'SELECT "{safe_col}", (("{safe_col}" - {mean}) / {std}) AS z_score '
                    f"FROM read_parquet($1) "
                    f'WHERE ABS(("{safe_col}" - {mean}) / {std}) > {threshold} '
                    f"LIMIT 50",
                    [str(parquet)],
                ).fetchall()
                result["anomalies"] = [{column: r[0], "z_score": round(r[1], 2)} for r in rows]
                result["mean"] = round(mean, 4)
                result["std"] = round(std, 4)
                result["threshold"] = threshold
            break
    return result


def _tool_finetune(  # noqa: C901
    feature_set: str,
    target: str,
    algorithm: str = "random_forest",
    model_name: str = "",
) -> dict[str, Any]:
    """Train a sklearn model on a gold table and register it."""
    import contextlib as _ctx

    result: dict[str, Any] = {
        "feature_set": feature_set,
        "target": target,
        "algorithm": algorithm,
    }
    try:
        import numpy as np  # type: ignore[import-untyped]
        import pandas as pd  # type: ignore[import-untyped]
        from sklearn.ensemble import (  # type: ignore[import-untyped]
            GradientBoostingClassifier,
            GradientBoostingRegressor,
            RandomForestClassifier,
            RandomForestRegressor,
        )
        from sklearn.linear_model import LogisticRegression, Ridge  # type: ignore[import-untyped]
        from sklearn.metrics import accuracy_score, r2_score  # type: ignore[import-untyped]
        from sklearn.model_selection import train_test_split  # type: ignore[import-untyped]

        from dex_studio._engine import get_engine

        eng = get_engine()
        if eng is None:
            return {"error": "No engine available"}

        # Load data from gold table via SQL
        df_result = _tool_query(f"SELECT * FROM {feature_set}")
        if hasattr(df_result, "to_pandas"):
            df = df_result.to_pandas()
        elif hasattr(df_result, "iloc"):
            df = df_result
        elif isinstance(df_result, list):
            df = pd.DataFrame(df_result)
        else:
            return {"error": "Could not load feature data"}

        if target not in df.columns:
            cols = list(df.columns)
            return {"error": f"Target '{target}' not found. Available columns: {cols}"}

        # Drop non-numeric and select features
        numeric_df = df.select_dtypes(include=[np.number]).dropna()
        if target not in numeric_df.columns:
            return {"error": f"Target '{target}' must be numeric"}

        feature_cols = [c for c in numeric_df.columns if c != target]
        if len(feature_cols) < 1:
            return {"error": "Not enough numeric feature columns"}

        X = numeric_df[feature_cols].values
        y = numeric_df[target].values

        if len(X) < 10:
            return {"error": "Not enough rows for training (need at least 10)"}

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Pick estimator
        is_classifier = len(np.unique(y)) <= 20 and np.issubdtype(y.dtype, np.integer)
        algo_map = {
            "random_forest": RandomForestClassifier if is_classifier else RandomForestRegressor,
            "gradient_boosting": (
                GradientBoostingClassifier if is_classifier else GradientBoostingRegressor
            ),
            "linear": LogisticRegression if is_classifier else Ridge,
        }
        EstClass = algo_map.get(algorithm, RandomForestRegressor)
        model = (
            EstClass(n_estimators=100, random_state=42)
            if hasattr(EstClass, "n_estimators")
            else EstClass()
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        metric = float(
            accuracy_score(y_test, y_pred) if is_classifier else r2_score(y_test, y_pred)
        )
        metric_name = "accuracy" if is_classifier else "r2_score"

        model.feature_names_in_ = np.array(feature_cols)  # type: ignore[attr-defined]

        # Register
        reg_name = model_name or f"{feature_set}_{target}_model"
        import pickle
        import time

        models_dir = eng.project_dir / ".dex" / "models" / reg_name
        models_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = models_dir / f"v{int(time.time())}.pkl"
        with open(artifact_path, "wb") as f:
            pickle.dump(model, f)

        registry_path = eng.project_dir / ".dex" / "models" / "registry.json"
        import json as _json

        reg: dict[str, list[Any]] = {}
        with _ctx.suppress(Exception):
            reg = _json.loads(registry_path.read_text())
        reg.setdefault(reg_name, []).append(
            {
                "artifact_path": str(artifact_path),
                "stage": "development",
                "algorithm": algorithm,
                "feature_names": feature_cols,
                "target": target,
            }
        )
        registry_path.write_text(_json.dumps(reg, indent=2))

        result.update(
            {
                "model_name": reg_name,
                "features": feature_cols,
                "rows_trained": len(X_train),
                metric_name: round(metric, 4),
                "artifact": str(artifact_path),
                "status": "registered",
            }
        )

    except Exception as exc:
        result["error"] = str(exc)

    return result
