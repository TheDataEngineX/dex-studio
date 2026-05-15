# DEX Studio — Design Document

## 1. Purpose

DEX Studio is a **local, Python-first, open-source UI application** that provides a single
control plane for end-to-end data projects powered by [TheDataEngineX/dex](https://github.com/TheDataEngineX/dex).

It does **not** fork or rebrand upstream DEX. It is a separate tool that connects to a local
DEX engine instance and unifies workflows in one place:

```
Project Setup → Ingestion → Medallion Pipelines → ML/AI → Serving → Observability
```

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      DEX Studio (Reflex)                          │
│                                                                   │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────────────────┐  │
│  │  Pages    │  │ Components │  │   State                      │  │
│  │  (views)  │  │ (shared)   │  │   (Reflex State classes)     │  │
│  └─────┬─────┘  └─────┬──────┘  └─────────────┬──────────────┘  │
│        │               │                        │                 │
│  ┌─────┴───────────────┴────────────────────────┴──────────────┐  │
│  │                     Studio Core                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐                │  │
│  │  │  Config   │  │  Engine  │  │   Theme    │                │  │
│  │  │  (YAML)   │  │ (direct) │  │  (Reflex)  │                │  │
│  │  └──────────┘  └──────────┘  └────────────┘                │  │
│  └──────────────────────────┬──────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              │  direct import (same process)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    DEX Engine (dataenginex)                        │
│  Registry · Config · ML · AI · Observability · Workflows          │
└──────────────────────────────────────────────────────────────────┘
```

DEX Studio embeds the `dataenginex` package directly (no HTTP hop) via `DexEngine` in
`src/dex_studio/engine.py`. A separate DEX API server is not required for local use.

### Why Reflex

| Requirement | Reflex Capability |
| --- | --- |
| Python-first, no manual JS build step | ✅ Python components compile to React |
| Real URL routing (`/data`, `/ml`, `/ai`) | ✅ `@rx.page` decorator |
| Reactive state for live updates | ✅ Built-in async State classes |
| Web-based (browser or embedded) | ✅ Serves on configurable port (7860) |
| Type-safe component model | ✅ Full mypy strict compatibility |
| Auth middleware (future) | ✅ FastAPI middleware support |

### Why NOT Streamlit

- No real URL routing (query params only)
- No background tasks (script re-executes on every interaction)
- Performance degrades with complex layouts
- Can't embed into existing FastAPI infrastructure

## 3. Project Structure

```
dex-studio/
├── pyproject.toml                  # Hatchling build, deps
├── rxconfig.py                     # Reflex config (ports, app_name)
├── src/
│   └── dex_studio/
│       ├── __init__.py             # Package + version
│       ├── cli.py                  # CLI entry (dex-studio command)
│       ├── app.py                  # Reflex app + page registrations
│       ├── config.py               # YAML config loading
│       ├── engine.py               # DexEngine class (wraps dataenginex)
│       ├── _engine.py              # DexEngine singleton
│       ├── state/
│       │   ├── base.py             # Base Reflex State
│       │   ├── data.py             # Data domain state
│       │   ├── ml.py               # ML domain state
│       │   ├── ai.py               # AI domain state
│       │   └── system.py           # System/config state
│       ├── components/
│       │   └── layout.py           # Sidebar, header, page_shell
│       └── pages/
│           ├── data/               # Data domain pages
│           ├── ml/                 # ML domain pages
│           ├── ai/                 # AI domain pages
│           └── system/             # System/settings pages
├── tests/
│   ├── conftest.py
│   └── unit/
└── docs/
    └── design.md                   # This document
```

## 4. Configuration

Config is loaded with this priority (highest wins):

1. CLI arguments (`--url`, `--token`, `--theme`)
1. Environment variables (`DEX_STUDIO_API_URL`, `DEX_STUDIO_API_TOKEN`, …)
1. Project-local `.dex-studio.yaml`
1. User-level `~/.dex-studio/config.yaml`
1. Built-in defaults

```yaml
# ~/.dex-studio/config.yaml
api_url: "http://localhost:17000"
api_token: null
timeout: 10.0
theme: dark
poll_interval: 5.0
```

Key environment variables used by the container:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEX_STUDIO_HOST` | `0.0.0.0` | Bind address |
| `DEX_STUDIO_PORT` | `7860` | Frontend port |
| `DEX_STUDIO_API_URL` | `http://localhost:17000` | DEX engine URL |

## 5. Lockstep Development Model

Each Studio page drives corresponding DEX engine API endpoints.
When Studio needs data that DEX doesn't expose yet, the engine API must be extended first.

| Studio Domain | DEX Engine Backends Required | Status |
| --- | --- | --- |
| Data | `GET /api/v1/data/quality`, `/api/v1/warehouse/layers`, `/api/v1/data/sources` | ✅ Available |
| ML | `GET /api/v1/models`, `POST /api/v1/predict` | ✅ Available |
| AI | Routing, runtime, memory, observability backends | ✅ Available |
| System | Config, registry, health | ✅ Available |

### Lockstep Rule

> **No Studio page without a DEX API endpoint. No DEX API endpoint without a Studio page.**

## 6. Technology Choices

| Choice | Rationale |
| --- | --- |
| **Reflex** | Python-first, real routing, reactive state, compiles to React |
| **dataenginex (direct)** | Direct package import — no HTTP overhead for local use |
| **DuckDB** | Embedded analytics for Studio-local queries |
| **structlog** | Structured logging, matches DEX engine patterns |
| **Pydantic** | Config validation, matches DEX engine patterns |
| **Hatchling** | Same build backend as DEX engine |
| **Separate repo** | Different release cadence, users, and dependency trees |

## 7. Deployment

DEX Studio ships as a Docker image (`ghcr.io/thedataenginex/dex-studio`) deployed via
ArgoCD from [TheDataEngineX/infradex](https://github.com/TheDataEngineX/infradex).

Environments:

| Environment | Overlay | Triggered by |
| --- | --- | --- |
| Preview | `argocd/previews/dex-studio/<branch>/` | Push to feature branch (auto) |
| Stage | `argocd/overlays/dex-studio-stage/` | Promote workflow (manual) |
| Prod | `argocd/overlays/dex-studio-prod/` | Promote workflow (manual, after stage) |

Promotion: **dex-studio → Actions → Promote Image** — pick `environment` and `source_branch`.

## 8. Phased Roadmap

### Phase 0 — Foundation (v0.1.0) ✅

- Project scaffold + CI
- Config system (file + env + CLI)
- DEX engine lockstep: mount ML router

### Phase 1 — Data Operations (v0.2.0) ← current

- Data, ML, AI, System domain pages
- Reflex reactive state for live updates
- Containerised deployment via ArgoCD

### Phase 2 — ML Workflows (v0.3.0)

- Experiment comparison page
- Drift detection alerts
- Model promotion workflow

### Phase 3 — Observability (v0.4.0)

- Prometheus metrics charts
- Log viewer
- Trace explorer

### Phase 4 — Project Management (v0.5.0)

- Project scaffolder (`dex-studio init`)
- Config editor
- Multi-instance support

## 9. Non-Goals

- **Cloud deployment** — Studio is local-first; no hosted SaaS version
- **Multi-user auth** — single-user or small-team use
- **Data editing** — read-only dashboard; mutations are pipeline triggers only
- **Replacing Grafana** — Studio shows DEX-specific views, not generic metrics dashboards
