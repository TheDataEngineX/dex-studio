from __future__ import annotations

import reflex as rx

from dex_studio.pages.ai.agents import ai_agents
from dex_studio.pages.ai.collections import ai_collections
from dex_studio.pages.ai.cost import ai_cost

# ai pages
from dex_studio.pages.ai.dashboard import ai_dashboard
from dex_studio.pages.ai.hitl import ai_hitl
from dex_studio.pages.ai.memory import ai_memory
from dex_studio.pages.ai.playground import ai_playground
from dex_studio.pages.ai.rag_eval import ai_rag_eval
from dex_studio.pages.ai.retrieval import ai_retrieval
from dex_studio.pages.ai.router import ai_router
from dex_studio.pages.ai.sandbox import ai_sandbox
from dex_studio.pages.ai.tools import ai_tools
from dex_studio.pages.ai.traces import ai_traces
from dex_studio.pages.ai.vectors import ai_vectors
from dex_studio.pages.ai.workflows import ai_workflows
from dex_studio.pages.data.asset_graph import data_asset_graph
from dex_studio.pages.data.catalog import data_catalog
from dex_studio.pages.data.contracts import data_contracts

# data pages
from dex_studio.pages.data.dashboard import data_dashboard
from dex_studio.pages.data.lineage import data_lineage
from dex_studio.pages.data.pipelines import data_pipelines
from dex_studio.pages.data.quality import data_quality
from dex_studio.pages.data.sources import data_sources
from dex_studio.pages.data.sql_console import data_sql_console
from dex_studio.pages.data.templates import data_templates
from dex_studio.pages.data.warehouse import data_warehouse
from dex_studio.pages.ml.ab_test import ml_ab_test

# ml pages
from dex_studio.pages.ml.dashboard import ml_dashboard
from dex_studio.pages.ml.drift import ml_drift
from dex_studio.pages.ml.experiments import ml_experiments
from dex_studio.pages.ml.features import ml_features
from dex_studio.pages.ml.hyperopt import ml_hyperopt
from dex_studio.pages.ml.model_card import ml_model_card
from dex_studio.pages.ml.models import ml_models
from dex_studio.pages.ml.predictions import ml_predictions
from dex_studio.pages.ml.promotions import ml_promotions
from dex_studio.pages.onboarding import OnboardingState, onboarding

# other pages
from dex_studio.pages.project_hub import project_hub
from dex_studio.pages.system.activity import system_activity
from dex_studio.pages.system.components import system_components
from dex_studio.pages.system.connection import system_connection
from dex_studio.pages.system.incidents import system_incidents
from dex_studio.pages.system.logs import system_logs
from dex_studio.pages.system.metrics import system_metrics
from dex_studio.pages.system.settings import system_settings

# system pages
from dex_studio.pages.system.status import system_status
from dex_studio.pages.system.traces import system_traces
from dex_studio.state.ai import AIState
from dex_studio.state.data import DataState
from dex_studio.state.ml import MLState
from dex_studio.state.system import SystemState

app = rx.App(
    theme=rx.theme(
        appearance="dark",
        accent_color="indigo",
        gray_color="slate",
        radius="medium",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap",
        "studio.css",
    ],
    style={"font_family": "Fira Sans, Inter, system-ui, -apple-system, sans-serif"},
)

# data
app.add_page(data_dashboard, route="/data", on_load=DataState.load_pipelines)
app.add_page(data_pipelines, route="/data/pipelines", on_load=DataState.load_pipelines)
app.add_page(data_sources, route="/data/sources", on_load=DataState.load_sources)
app.add_page(data_sql_console, route="/data/sql")
app.add_page(data_warehouse, route="/data/warehouse", on_load=DataState.load_warehouse_layers)
app.add_page(data_lineage, route="/data/lineage", on_load=DataState.load_lineage)
app.add_page(data_quality, route="/data/quality", on_load=DataState.load_quality)
app.add_page(data_catalog, route="/data/catalog", on_load=DataState.load_sources)
app.add_page(data_asset_graph, route="/data/asset-graph", on_load=DataState.load_lineage)
app.add_page(data_contracts, route="/data/contracts")
app.add_page(data_templates, route="/data/templates")

# ml
app.add_page(ml_dashboard, route="/ml", on_load=MLState.load_models)
app.add_page(ml_models, route="/ml/models", on_load=MLState.load_models)
app.add_page(ml_experiments, route="/ml/experiments", on_load=MLState.load_experiments)
app.add_page(ml_predictions, route="/ml/predictions", on_load=MLState.load_models)
app.add_page(ml_features, route="/ml/features", on_load=MLState.load_features)
app.add_page(ml_drift, route="/ml/drift")
app.add_page(ml_hyperopt, route="/ml/hyperopt")
app.add_page(ml_ab_test, route="/ml/ab-test")
app.add_page(ml_model_card, route="/ml/model-card", on_load=MLState.load_models)
app.add_page(ml_promotions, route="/ml/promotions")

# ai
app.add_page(ai_dashboard, route="/ai", on_load=AIState.load_agents)
app.add_page(ai_agents, route="/ai/agents", on_load=AIState.load_agents)
app.add_page(ai_playground, route="/ai/playground", on_load=AIState.load_agents)
app.add_page(ai_traces, route="/ai/traces", on_load=AIState.load_traces)
app.add_page(ai_tools, route="/ai/tools", on_load=AIState.load_tools)
app.add_page(ai_memory, route="/ai/memory", on_load=AIState.load_memory)
app.add_page(ai_workflows, route="/ai/workflows", on_load=AIState.load_workflows)
app.add_page(ai_router, route="/ai/router")
app.add_page(ai_cost, route="/ai/cost")
app.add_page(ai_hitl, route="/ai/hitl")
app.add_page(ai_sandbox, route="/ai/sandbox")
app.add_page(ai_rag_eval, route="/ai/rag-eval")
app.add_page(ai_retrieval, route="/ai/retrieval")
app.add_page(ai_vectors, route="/ai/vectors", on_load=AIState.load_memory)
app.add_page(ai_collections, route="/ai/collections", on_load=AIState.load_memory)

# system
app.add_page(system_status, route="/system", on_load=SystemState.load_health)
app.add_page(system_logs, route="/system/logs", on_load=SystemState.load_logs)
app.add_page(system_metrics, route="/system/metrics", on_load=SystemState.load_metrics)
app.add_page(system_traces, route="/system/traces", on_load=SystemState.load_traces)
app.add_page(system_components, route="/system/components", on_load=SystemState.load_components)
app.add_page(system_activity, route="/system/activity")
app.add_page(system_incidents, route="/system/incidents")
app.add_page(system_settings, route="/system/settings")
app.add_page(system_connection, route="/system/connection")

# root
app.add_page(project_hub, route="/")
app.add_page(onboarding, route="/onboarding", on_load=OnboardingState.on_load)


def start(**kwargs: object) -> None:
    """Launch DEX Studio. Called by CLI; kwargs forwarded for config injection."""
    import os

    from dex_studio.config import StudioConfig

    config: StudioConfig | None = kwargs.get("config")  # type: ignore[assignment]
    if config is not None and config.local_config_path:
        os.environ.setdefault("DEX_CONFIG_PATH", config.local_config_path)
        from dex_studio._engine import init_engine

        init_engine(config.local_config_path)

    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "reflex", "run"], check=False)
