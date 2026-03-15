# DEX Studio — Design Document

## 1. Purpose

DEX Studio is a **local, Python-first, open-source UI application** that provides a single
control plane for end-to-end data projects powered by [TheDataEngineX/DEX](https://github.com/TheDataEngineX/DEX).

It does **not** fork or rebrand upstream DEX. It is a separate tool that connects to a local
DEX engine instance and unifies workflows in one place:

```
Project Setup → Ingestion → Medallion Pipelines → ML/AI → Serving → Observability
```

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        DEX Studio (NiceGUI)                      │
│                                                                   │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────────────────┐  │
│  │  Pages    │  │ Components │  │   State / Storage            │  │
│  │  (views)  │  │ (shared)   │  │   (NiceGUI app.storage)     │  │
│  └─────┬─────┘  └─────┬──────┘  └─────────────┬──────────────┘  │
│        │               │                        │                 │
│  ┌─────┴───────────────┴────────────────────────┴──────────────┐  │
│  │                     Studio Core                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐                │  │
│  │  │  Config   │  │  Client  │  │   Theme    │                │  │
│  │  │  (YAML)   │  │  (httpx) │  │  (CSS)     │                │  │
│  │  └──────────┘  └──────────┘  └────────────┘                │  │
│  └──────────────────────────┬──────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              │  HTTP (localhost:8000)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    DEX Engine (FastAPI)                           │
│  /health  /ready  /startup  /metrics                             │
│  /api/v1/data/*   /api/v1/warehouse/*   /api/v1/system/*         │
│  /api/v1/models   /api/v1/models/{name}  /api/v1/predict         │
└──────────────────────────────────────────────────────────────────┘
```

### Why NiceGUI + Native Mode

| Requirement | NiceGUI Capability |
|--------------------------------------|-------------------------------------------|
| Python-first, no JS build step | ✅ Pure Python components |
| Real URL routing (`/quality`, `/models`) | ✅ `@ui.page` decorator |
| Websocket for live updates | ✅ Built-in, auto-managed |
| Desktop-native window | ✅ `native=True` via pywebview |
| Built on FastAPI | ✅ Same stack as DEX engine |
| Component model (cards, tables, tabs)| ✅ Quasar + custom components |
| Auth middleware (future) | ✅ FastAPI middleware support |

### Why NOT Streamlit

- No real URL routing (query params only)
- No websocket support (polling via rerun loop)
- No background tasks (script re-executes on every interaction)
- Performance degrades with complex layouts
- Can't embed into existing FastAPI infrastructure

## 3. Project Structure

```
dex-studio/
├── pyproject.toml                  # Hatchling build, deps
├── .python-version                 # 3.11
├── config/
│   └── default.yaml                # Default config template
├── src/
│   └── dex_studio/
│       ├── __init__.py             # Package + version
│       ├── cli.py                  # CLI entry (dex-studio command)
│       ├── app.py                  # NiceGUI app bootstrap
│       ├── config.py               # YAML config loading
│       ├── client.py               # httpx DEX API client
│       ├── theme.py                # CSS theme + colour palette
│       ├── components/
│       │   ├── sidebar.py          # Navigation sidebar
│       │   ├── status_card.py      # Health status cards
│       │   ├── metric_card.py      # Metric display cards
│       │   └── page_layout.py      # Sidebar + content wrapper
│       └── pages/
│           ├── overview.py         # Dashboard (/)
│           ├── health.py           # Health probes (/health)
│           ├── data_quality.py     # Medallion quality (/quality)
│           ├── lineage.py          # Lineage explorer (/lineage)
│           ├── ml_models.py        # Model registry (/models)
│           └── settings.py         # Connection config (/settings)
├── tests/
│   ├── conftest.py
│   └── unit/
│       ├── test_config.py
│       ├── test_client.py
│       └── test_cli.py
└── docs/
    └── DESIGN.md                   # This document
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
api_url: "http://localhost:8000"
api_token: null
timeout: 10.0
theme: dark
poll_interval: 5.0
window_width: 1400
window_height: 900
```

## 5. Lockstep Development Model

Each Studio page drives corresponding DEX engine API endpoints.
When Studio needs data that DEX doesn't expose yet, the engine API must be extended first.

| Studio Page | DEX Engine Endpoints Required | Status |
|-----------------|-------------------------------------------------------------|------------|
| Overview | `GET /`, `/health`, `/startup`, `/api/v1/data/quality`, `/api/v1/system/config` | ✅ Available |
| Health | `GET /health`, `/ready`, `/startup` | ✅ Available |
| Data Quality | `GET /api/v1/data/quality`, `/api/v1/data/quality/{layer}`, `/api/v1/data/sources`, `/api/v1/warehouse/layers` | ✅ Available |
| Lineage | `GET /api/v1/warehouse/lineage/{event_id}` | ✅ Available |
| ML Models | `GET /api/v1/models`, `/api/v1/models/{name}`, `POST /api/v1/predict` | 🔧 Router exists but was unmounted — **fixed in lockstep** |
| Settings | (local only — no API calls) | ✅ N/A |

### Lockstep Rule

> **No Studio page without a DEX API endpoint. No DEX API endpoint without a Studio page.**

Future pages (pipelines, ingestion, drift detection) require new DEX engine endpoints.
Those endpoints and pages are developed together in coordinated PRs across both repos.

## 6. DEX Engine Changes (v0.3.x Lockstep)

### ML Router Mounted

The ML router (`ml_router` in `dataenginex.api.routers.ml`) existed but was never
`include_router()`'d in the CareerDEX app. Fixed by adding:

```python
from dataenginex.api.routers.ml import ml_router
app.include_router(ml_router)
```

This activates 3 previously dead endpoints:

- `POST /api/v1/predict`
- `GET /api/v1/models`
- `GET /api/v1/models/{name}`

## 7. Technology Choices

| Choice | Rationale |
|---------------------------|----------------------------------------------------------|
| **NiceGUI** | Python-first, real routing, websockets, built on FastAPI |
| **pywebview (native mode)** | Desktop-native window without Electron overhead |
| **httpx** | Async HTTP client, connection pooling, same API as requests |
| **Pydantic** | Config validation, matches DEX engine patterns |
| **PyYAML** | Config file format |
| **Hatchling** | Same build backend as DEX engine |
| **Separate repo** | Different release cadence, users, and dependency trees |

## 8. Phased Roadmap

### Phase 0 — Foundation (v0.1.0) ← current

- Project scaffold + CI
- httpx client with health check
- YAML config system (file + env + CLI)
- 6 pages: Overview, Health, Quality, Lineage, ML Models, Settings
- DEX engine lockstep: mount ML router

### Phase 1 — Data Operations (v0.2.0)

- Pipeline trigger page (needs `POST /api/v1/pipelines/run` on DEX engine)
- Ingestion management (needs `POST /api/v1/data/ingest`)
- Live pipeline log streaming (NiceGUI websocket)

### Phase 2 — ML Workflows (v0.3.0)

- Experiment comparison page
- Drift detection alerts (needs `GET /api/v1/ml/drift`)
- Model promotion workflow

### Phase 3 — Observability (v0.4.0)

- Prometheus metrics charts (needs structured `GET /api/v1/metrics` JSON endpoint)
- Log viewer (needs `GET /api/v1/logs`)
- Trace explorer (needs `GET /api/v1/traces`)

### Phase 4 — Project Management (v0.5.0)

- Project scaffolder (`dex-studio init`)
- Config editor (edit DEX engine config from Studio)
- Multi-instance support (connect to multiple DEX engines)

## 9. Non-Goals (v0.1.0)

- **Cloud deployment** — Studio is local-first; no hosted SaaS version
- **Multi-user auth** — single-user desktop app
- **Data editing** — read-only dashboard; mutations are pipeline triggers only
- **Replacing Grafana** — Studio shows DEX-specific views, not generic metrics dashboards
- **Package on PyPI** — distribute via GitHub releases for now
