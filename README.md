# DEX Studio

[![CI](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**DEX Studio** — self-hosted web UI for the [DataEngineX](https://github.com/TheDataEngineX/dex) platform.
Single control plane for Data · ML · AI · System · Career intelligence.

Built on [Reflex](https://reflex.dev) — Python-first reactive web framework (Python → React).

---

## Quick Start

```bash
git clone https://github.com/TheDataEngineX/dex-studio && cd dex-studio
uv sync

# Start DEX engine first
cd ../dex && uv run poe dev          # starts at http://localhost:17000

# Launch Studio
cd ../dex-studio && uv run poe dev   # starts at http://localhost:7860
```

---

## Pages

| Domain | Pages |
|--------|-------|
| Data | Dashboard, Pipelines, Sources, SQL Console, Warehouse, Lineage, Quality, Catalog, Asset Graph |
| ML | Dashboard, Models, Experiments, Predictions, Features, Drift, A/B Tests, Model Cards |
| AI | Dashboard, Agents, Playground, Traces, Tools, Memory, Workflows, Router, Cost, HITL, RAG Eval |
| System | Status, Logs, Metrics, Traces, Components, Activity, Incidents, Settings, Connection |
| Career | Powered by [CareerDEX](https://github.com/TheDataEngineX/careerdex) |

---

## Configuration

```bash
export DEX_API_URL=http://localhost:17000   # default
```

Config file: `~/.dex-studio/config.yaml`

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| UI Framework | Reflex 0.7+ (Python → React) |
| HTTP Client | httpx (async) |
| Config | PyYAML + Pydantic |
| Build | Hatchling + uv |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Type Checking | mypy (strict) |

---

## Development

```bash
uv run poe lint          # ruff lint
uv run poe typecheck     # mypy strict
uv run poe test          # pytest
uv run poe check-all     # lint + typecheck + test
uv run poe dev           # Reflex dev server (port 7860)
```

---

**Version**: [![Release](https://img.shields.io/github/v/release/TheDataEngineX/dex-studio)](https://github.com/TheDataEngineX/dex-studio/releases) | **License**: MIT
