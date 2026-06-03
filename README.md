# DEX Studio

[![CI](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Open-source, self-hosted, local-first Data + ML + AI workbench for individuals and small teams. One Docker command. Your data never leaves your laptop.**

> _Demo GIF lands in v0.5 (see [roadmap](https://github.com/TheDataEngineX/docs/blob/main/docs/roadmap/DESIGN-2026.md))._ Today the studio is functional but the polished CSV → train classifier → ask-questions-with-LLM walkthrough is the next milestone.

______________________________________________________________________

## Run it in 60 seconds

```bash
git clone https://github.com/TheDataEngineX/dex-studio && cd dex-studio
docker compose up
# open http://localhost:7860
```

Or run locally without Docker:

```bash
uv sync
uv run poe dev                          # http://localhost:7860 with hot-reload
```

Point it at a specific config:

```bash
dex-studio --config /path/to/dex.yaml
```

______________________________________________________________________

## What you get

Single page-of-glass UI for everything the [`dataenginex`](https://github.com/TheDataEngineX/dex) library does — no separate API server, no microservices.

| Domain | Today | Phase 2/3 of [roadmap](https://github.com/TheDataEngineX/docs/blob/main/docs/roadmap/DESIGN-2026.md) |
| --- | --- | --- |
| **Data** | Sources (CSV, Parquet, Postgres, Spark, dbt), Pipelines, SQL console, Warehouse (bronze/silver/gold), Lineage graph, Quality checks, Catalog | SQL transform editor, streaming source monitor, ER diagram view |
| **ML** | Model registry, Experiments tracker, Drift detection, Feature store, Predictions | Per-experiment artifact view, prediction history, A/B test runner |
| **AI** | Agents, Playground (SSE streaming chat), Memory browser, Tool registry, Trace viewer, Workflow list | Tool-call cards, conversation persistence, YAML workflow editor |
| **Privacy** | PrivacyGuard overview, PII strategy config, Audit log, Alert rules (pipeline failure + drift) | Outbound-call quarantine, policy editor, budget threshold alerts |
| **System** | Status, Live log tail (SSE), Metrics, Runs feed (filter by type/status), Cost dashboard | Unified timeline, Slack/email alert channels |
| **Dashboards** | — | Vega-Lite chart grids built from SQL queries |

______________________________________________________________________

## Local-first by default

- DuckDB is embedded — no Postgres / Redis required for the base install
- LLM defaults to [Ollama](https://ollama.com) running locally; OpenAI / Anthropic are opt-in
- Optional integrations gated behind `dataenginex` extras (`[postgres]`, `[qdrant]`, `[cloud]`, …)
- Every outbound network call is logged; PII guardrails mask sensitive fields before any external request
- All data lives in `.dex/` next to your project — copy the folder, move machines, you're done

______________________________________________________________________

## Configuration

```bash
export DEX_STUDIO_API_KEY=your-key       # optional — disables auth if unset
export DEX_STUDIO_HOST=0.0.0.0           # default
export DEX_STUDIO_PORT=7860              # default
```

Projects registry: `~/.dex-studio/projects.yaml` — switch between projects via the sidebar dropdown.

______________________________________________________________________

## Tech stack

| Component | Technology |
| --- | --- |
| Server | FastAPI + Uvicorn |
| Templates | Jinja2 (server-rendered HTML) |
| Interactivity | HTMX + Alpine.js |
| Styling | Custom CSS + Radix UI design tokens |
| Engine | [`dataenginex`](https://github.com/TheDataEngineX/dex) — direct import, no HTTP hop |
| Config | PyYAML + Pydantic |
| Build | Hatchling + uv |
| Testing | pytest + httpx TestClient |
| Linting / Types | Ruff + mypy strict |

The frontend stack is frozen for 12 months (no React/Vue/Svelte) — see [ADR-0007](https://github.com/TheDataEngineX/docs/blob/main/adr/0007-local-first-scope-reset.md).

______________________________________________________________________

## Development

```bash
uv run poe lint              # ruff lint
uv run poe lint-fix          # ruff lint + auto-fix
uv run poe typecheck         # mypy strict
uv run poe test              # pytest
uv run poe check-all         # lint + typecheck + test
uv run poe dev               # uvicorn dev server (port 7860, hot-reload)
```

Design system reference for contributors: [DESIGN-BRIEF-2026.md](DESIGN-BRIEF-2026.md) (the brief used to commission the v0.5 visual design) — see also `src/dex_studio/static/studio.css` for current tokens.

______________________________________________________________________

## Ecosystem

| Repo | Purpose |
| --- | --- |
| [dataenginex](https://github.com/TheDataEngineX/dex) | The Python library (PyPI) — engine, config, all backends |
| [dex-studio](https://github.com/TheDataEngineX/dex-studio) | This repo — web UI |
| [docs](https://github.com/TheDataEngineX/docs) | Documentation site — ADRs + 10-week roadmap |

______________________________________________________________________

## Status

Pre-1.0, rebuilding scope through v0.5. See the [DEX scope-reset CHANGELOG](https://github.com/TheDataEngineX/dex/blob/main/CHANGELOG.md) for the rationale and the [2026 roadmap](https://github.com/TheDataEngineX/docs/blob/main/docs/roadmap/DESIGN-2026.md) for what ships next.

______________________________________________________________________

**License:** MIT • **Python:** 3.13+ • **Port:** 7860
