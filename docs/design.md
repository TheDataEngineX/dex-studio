# DEX Studio — Design Document

## 1. Purpose

DEX Studio is a **local, Python-first, open-source web UI** that provides a single
control plane for end-to-end data projects powered by [TheDataEngineX/dataenginex](https://github.com/TheDataEngineX/dataenginex).

It does **not** fork or rebrand upstream DEX. It imports `dataenginex` directly as a library
and unifies all workflows in one place:

```text
Project Setup → Ingestion → Medallion Pipelines → ML/AI → Observability
```

## 2. Architecture

```mermaid
graph TB
    subgraph ACTORS["Actors"]
        DEV["Data Engineer / Scientist"]
        OPS["Platform Operator"]
        CONSUMER["Business User"]
    end

    subgraph STUDIO["DEX Studio — Control Plane"]
        UI["Web UI<br/>FastAPI · Jinja2 · HTMX · Alpine.js<br/>Port 7860"]
        AUTH["Auth Layer<br/>Session · PBKDF2 · OIDC"]
        SCHED["Orchestration<br/>Scheduler · Backfill · Compaction"]
        CORE["Core Services<br/>StudioDb · Watermark · Execution<br/>Quality · Schema Evolution · Notify"]
        ENGINE["Engine Bridge<br/>DexEngine Singleton — direct import"]
    end

    subgraph DEX["dataenginex — Engine Layer"]
        CONFIG["Config System<br/>dex.yaml · Pydantic · Env vars"]
        PIPELINES["Pipeline Engine<br/>DAG runner · Transforms · Quality"]
        STORE["DexStore<br/>DuckDB · Lineage · Audit"]
        ML["ML Engine<br/>Train · Registry · Serve · Drift"]
        AI["AI Engine<br/>LLMs · Agents · RAG · Vectors"]
        SEC["PrivacyGuard<br/>PII · Masking · Audit"]
    end

    subgraph STORAGE["Storage Layer"]
        DUCK[("DuckDB<br/>Embedded")]
        PG[("PostgreSQL<br/>Optional — Multi-pod")]
        S3[("S3 / GCS / BigQuery")]
        QDRANT[("Qdrant<br/>Vector store")]
        ES[("Elasticsearch<br/>Search")]
    end

    subgraph STREAM["Streaming & Queue"]
        KAFKA[("Kafka")]
        RABBIT[("RabbitMQ")]
        REDIS[("Redis — ARQ jobs")]
    end

    subgraph LLM_LAYER["LLM Layer"]
        OLLAMA[("Ollama — Local")]
        REMOTE[("OpenAI / Anthropic")]
        LITELLM[("LiteLLM — Routing")]
    end

    subgraph INFRA["Infrastructure"]
        DOCKER["Docker Compose"]
        K8S["Kubernetes + ArgoCD"]
        MONITOR["Prometheus · Alerts"]
    end

    subgraph INTEGRATIONS["Enterprise Integrations"]
        AUTHENTIK[("Authentik OIDC")]
        MLFLOW[("MLflow Tracking")]
        SPARK[("PySpark")]
        DBT[("dbt CLI")]
    end

    DEV -->|"HTTP / SSE"| UI
    OPS -->|"Config · Monitor"| UI
    CONSUMER -->|"Dashboards"| UI
    UI --> AUTH
    UI --> SCHED
    UI --> CORE
    CORE --> ENGINE
    ENGINE --> DEX
    DEX --> CONFIG
    DEX --> PIPELINES
    DEX --> STORE
    DEX --> ML
    DEX --> AI
    DEX --> SEC
    PIPELINES --> DUCK
    PIPELINES -->|"optional"| PG
    PIPELINES -->|"ingest"| KAFKA
    PIPELINES -->|"ingest"| RABBIT
    PIPELINES -->|"optional"| S3
    PIPELINES -->|"optional"| SPARK
    PIPELINES -->|"optional"| DBT
    ML -->|"track"| MLFLOW
    ML -->|"optional"| ES
    AI -->|"store"| QDRANT
    AI -->|"default"| OLLAMA
    AI -->|"opt-in"| REMOTE
    AI -->|"route"| LITELLM
    CORE -->|"multi-pod"| PG
    STUDIO -->|"Docker"| DOCKER
    STUDIO -->|"K8s"| K8S
    AUTH -->|"SSO"| AUTHENTIK
    K8S --> MONITOR

    linkStyle 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28 stroke-width:1px
```

Studio mounts `dataenginex` via `DexEngine` (see `src/dex_studio/_engine.py`). No separate server process is required — the engine is imported directly into the same process. Pipeline DAG resolution lives in `dataenginex.data.pipeline.dag`.

### Why FastAPI + Jinja2 + HTMX

| Requirement | Approach |
| --- | --- |
| Server-side rendering (fast initial load) | Jinja2 templates |
| Partial page updates without a JS build step | HTMX attributes |
| Type-safe route handlers | FastAPI + Pydantic |
| Direct library access (no HTTP hop) | `dataenginex` imported in-process |
| Standard Python tooling | pytest TestClient, mypy strict |

## 3. Project Structure

```text
dex-studio/
├── pyproject.toml                  # Hatchling build, deps, poe tasks
├── src/
│   └── dex_studio/
│       ├── __init__.py             # Package + version
│       ├── app.py                  # FastAPI factory — mounts routers, templates, static
│       ├── cli.py                  # CLI entry (dex-studio --host --port)
│       ├── config.py               # StudioPrefs + ProjectEntry (projects.yaml, prefs.yaml)
│       ├── auth.py                 # Session-based auth (PBKDF2 + rate limiter)
│       ├── oidc.py                 # Authentik OIDC auth support
│       ├── _engine.py              # DexEngine singleton (get_engine / set_engine)
│       ├── _json.py                # orjson-backed JSON helpers
│       ├── utils.py                # Shared template helpers
│       ├── nav.py                  # Sidebar nav structure
│       ├── flow.py                 # Pipeline DAG utilities for the UI
│       ├── studio_db.py            # Dual-backend persistence (SQLite/PostgreSQL)
│       ├── scheduler.py            # Async cron scheduler
│       ├── jobs.py                 # Background task lifecycle
│       ├── watermark.py            # Ingestion watermark + hash dedup
│       ├── backfill.py             # Pipeline backfill engine
│       ├── compaction.py           # Parquet file compaction
│       ├── execution.py            # Pipeline execution tracking
│       ├── embeddings.py           # Embedding management UI
│       ├── quality_eval.py         # Data quality evaluation
│       ├── run_checks.py           # Run quality checks
│       ├── schema_evolution.py     # Schema evolution management
│       ├── notify.py               # Event notification dispatch
│       ├── store.py                # Store abstraction
│       ├── db_store.py             # DB store helpers
│       ├── logging_setup.py        # Structlog configuration
│       ├── logstore.py             # In-app log capture + storage
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── root.py             # Home, project selector, health
│       │   ├── data.py             # Data domain routes
│       │   ├── intelligence.py     # Intelligence domain routes
│       │   ├── secops.py           # SecOps domain routes
│       │   ├── system.py           # System domain routes
│       │   ├── content.py          # Content domain routes
│       │   ├── api.py              # API routes
│       │   └── _deps.py            # Shared FastAPI deps (engine, auth, render)
│       ├── templates/
│       │   ├── base.html           # Layout shell (sidebar, nav)
│       │   ├── components/         # Macros and shared components
│       │   ├── data/               # Data domain templates
│       │   ├── intelligence/       # Intelligence domain templates
│       │   ├── secops/             # SecOps domain templates
│       │   ├── system/             # System domain templates
│       │   ├── content/            # Content domain templates
│       │   └── partials/           # HTMX fragments
│       └── static/
│           └── studio.css          # Styles
├── scripts/
│   ├── demo/
│   │   ├── browser_segments.py     # Playwright screenshot capture
│   │   └── record.py               # Playwright video recording
│   └── seed_moviedex.py            # Demo data seeding
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── system/
│   ├── security/
│   ├── performance/
│   └── regression/
└── docs/
    └── design.md                   # This document
```

## 4. Configuration

```yaml
# ~/.dex-studio/projects.yaml  — registered projects
projects:
  - name: my-project
    path: /home/user/workspace/my-project/dex.yaml
```

```yaml
# ~/.dex-studio/prefs.yaml  — UI preferences
theme: dark
last_project: my-project
```

Key environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEX_STUDIO_HOST` | `0.0.0.0` | Bind address |
| `DEX_STUDIO_PORT` | `7860` | Port |
| `DEX_STUDIO_SESSION_SECRET` | auto-generated | Cookie signing key |

## 5. Development Model

Each Studio page calls `DexEngine` methods directly. When Studio needs data that
`dataenginex` doesn't expose yet, the library must be extended first.

| Studio Domain | DexEngine Methods Used |
| --- | --- |
| Data | `run_pipeline`, `source_schema`, `source_sample`, `warehouse_layers`, `warehouse_tables`, `quality_checks` |
| Intelligence | `model_registry.list_models`, `model_registry.predict`, `agents[name].chat`, `drift_detector`, `embedding_search` |
| Content | content-feed, recommendation-compare, watch-provider, cross-source match |
| System | `health`, `config`, `store.list_pipeline_runs` |

### Rule

> **No Studio page without a DexEngine method. No DexEngine method without a Studio page.**

### ML + AI Architecture

```mermaid
flowchart TB
    subgraph FEATURES["Feature Engineering"]
        F1["Raw features from Gold tables"]
        F2["Transform: Normalize · Encode · Embed"]
        F3["Feature store for serving"]
    end

    subgraph TRAINING["Training Pipeline"]
        T1["Train/Test/Val split"]
        T2["scikit-learn · XGBoost · PyTorch"]
        T3["MLflow tracking: params · metrics · artifacts"]
        T4["Register to Model Registry"]
    end

    subgraph SERVING["Serving"]
        S1["Predict API<br/>model_registry.predict()"]
        S2["Batch predict via scheduled pipeline"]
        S3["Drift detection: feature + model drift"]
    end

    subgraph RAG["RAG Pipeline"]
        R1["Documents → Chunks → Embed"]
        R2["Store: Qdrant / DuckDB VSS"]
        R3["Retrieve: BM25 + Dense Hybrid"]
        R4["Generate: Ollama · OpenAI · Anthropic"]
    end

    subgraph AGENTS["Agent Runtime"]
        A1["Chat interface with tools"]
        A2["Conversation + episodic memory"]
        A3["PrivacyGuard guardrails"]
    end

    FEATURES --> TRAINING
    TRAINING --> SERVING
    SERVING -->|"feature drift"| FEATURES
    FEATURES --> RAG
    RAG --> AGENTS
```

## 6. Technology Choices

| Choice | Rationale |
| --- | --- |
| **FastAPI** | Standard ASGI, type-safe, TestClient for unit tests |
| **Jinja2** | Server-side rendering, no JS build pipeline |
| **HTMX** | Partial updates via HTTP attributes — minimal JS footprint |
| **dataenginex (direct import)** | No HTTP overhead; single process for local use |
| **DuckDB (via DexStore)** | Embedded persistence — zero ops |
| **Separate repo** | Different release cadence, users, and dependency trees |

## 7. Deployment

```mermaid
flowchart TB
    subgraph DEV["Local Development"]
        DEV_DOCKER["docker compose up<br/>Port 7860 · SQLite backend"]
        DEV_NATIVE["uv run poe dev<br/>Port 7860 · Hot-reload"]
    end

    subgraph CI_CD["CI/CD Pipeline"]
        GIT["GitHub — push to main"]
        CI_WF["CI: lint · test · build"]
        RELEASE["Release: push tag v*.*.*"]
        REGISTRY[("ghcr.io<br/>Container registry")]
    end

    subgraph PROD["Production — Kubernetes via ArgoCD"]
        ARGO["ArgoCD<br/>GitOps sync"]
        DEPLOY["Deployment<br/>2 replicas + canary"]
        SVC["Service + Ingress<br/>dex-studio.example.com"]
        STATE[("PostgreSQL<br/>Multi-pod state")]
        MON["Prometheus · Alerts<br/>OOM · High CPU · Down"]
    end

    DEV_NATIVE --> GIT
    GIT --> CI_WF --> RELEASE --> REGISTRY
    REGISTRY -->|"image pull"| ARGO
    ARGO --> DEPLOY --> SVC
    DEPLOY --> STATE
    DEPLOY --> MON
```

DEX Studio ships as a Docker image (`ghcr.io/thedataenginex/dex-studio`) deployed on Kubernetes via ArgoCD from [TheDataEngineX/infradex](https://github.com/TheDataEngineX/infradex). Run locally with `docker compose up`.

### Quality Attributes

| Attribute | How It's Achieved |
|-----------|-------------------|
| **Availability** | Multi-pod deployment (2 replicas), canary deploys, health checks |
| **Scalability** | Stateless app pods, PostgreSQL-backed state for multi-pod, async worker pool |
| **Security** | Session auth, CSRF tokens, security headers, PII guardrails, SQL sandbox, vulnerability scanning |
| **Maintainability** | Direct import (no microservices), modular router structure, ABC + Registry pattern |
| **Observability** | Structured logging, Prometheus metrics, OpenTelemetry tracing, in-app log viewer |
| **Data Locality** | Local-first — DuckDB embedded, Ollama default, data stays on-device |
| **Resilience** | Pipeline retry + dead letter, scheduler leader election, graceful fallbacks on external deps |
| **Testability** | pytest TestClient, mypy strict, integration/system/security test suites |

## 8. Roadmap

### Phase 0 — Foundation ✅

- Version 0.5.2 — all phases delivered

- FastAPI app factory + router scaffold

- DexEngine singleton integration

- Session auth + config system

- CI pipeline

### Phase 1 — Data & ML ✅

- Data domain: sources, pipelines, warehouse, quality, lineage
- ML domain: models, experiments, predictions, drift
- AI domain: agents, playground
- System domain: status, logs, metrics, components

### Phase 2 — Interactivity ✅

- HTMX-driven partial updates (live pipeline status, metric charts)
- Pipeline run trigger UI
- Model promotion workflow

### Phase 3 — Multi-Project ✅

- Project switcher
- Config editor
- Multi-instance support (PostgreSQL backend, dual-replica ArgoCD)

## 9. Screenshots

| Domain | Preview |
| --- | --- |
| Hub | ![Hub](../docs/screenshots/hub.png) |
| Data — Pipelines | ![Pipelines](../docs/screenshots/data-pipelines.png) |
| Data — Sources | ![Sources](../docs/screenshots/data-sources.png) |
| Data — SQL Console | ![SQL Console](../docs/screenshots/data-sql.png) |
| Data — Quality | ![Quality](../docs/screenshots/data-quality.png) |
| Data — Lineage | ![Lineage](../docs/screenshots/data-lineage.png) |
| Intelligence — Playground | ![Playground](../docs/screenshots/intelligence-playground.png) |
| Intelligence — Models | ![Models](../docs/screenshots/intelligence-models.png) |
| Intelligence — Agents | ![Agents](../docs/screenshots/intelligence-agents.png) |
| Intelligence — Traces | ![Traces](../docs/screenshots/intelligence-traces.png) |
| SecOps — Overview | ![SecOps](../docs/screenshots/secops-overview.png) |
| System — Status | ![Status](../docs/screenshots/system-status.png) |
| System — Logs | ![Logs](../docs/screenshots/system-logs.png) |
| System — Scheduler | ![Scheduler](../docs/screenshots/system-scheduler.png) |
| System — Runs | ![Runs](../docs/screenshots/system-runs.png) |

## 10. Non-Goals

- **Cloud deployment** — Studio is local-first; no hosted SaaS version
- **Multi-user auth** — single-user or small-team use
- **Data editing** — read-only; mutations are pipeline triggers only
- **Replacing Grafana** — Studio shows DEX-specific views, not generic metric dashboards
