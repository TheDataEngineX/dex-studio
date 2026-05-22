# DEX Studio

[![CI](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**DEX Studio** — self-hosted web UI for the [DataEngineX](https://github.com/TheDataEngineX/dex) platform.
Single control plane for Data · ML · AI · System.

Built on FastAPI + Jinja2 + HTMX. Imports `dataenginex` directly — no separate API server needed.

---

## Architecture

DEX Studio is Layer 2 in the three-layer DEX architecture:

```text
Layer 1: dataenginex (library)  — PyPI package, DexEngine, DexStore, CLI
     ↓ direct Python import (same process)
Layer 2: DEX Studio (shell)     — this repo, FastAPI + Jinja2 + HTMX
     ↓ page router registration
Layer 3: Domain Apps            — register custom pages into Studio
```

Studio imports `dataenginex` as a library via `DexEngine`. No HTTP hop to a separate engine process.

---

## Quick Start

```bash
git clone https://github.com/TheDataEngineX/dex-studio && cd dex-studio
uv sync

# Launch Studio (opens with an empty project list)
uv run poe dev   # http://localhost:7860

# Or point to a specific dex.yaml
dex-studio --config /path/to/dex.yaml
```

---

## Pages

| Domain | Pages |
|--------|-------|
| Data | Dashboard, Pipelines, Sources, SQL Console, Warehouse, Lineage, Quality, Catalog |
| ML | Dashboard, Models, Experiments, Predictions, Drift |
| AI | Dashboard, Agents, Playground |
| System | Status, Logs, Metrics, Components |

---

## Configuration

```bash
export DEX_STUDIO_API_KEY=your-key   # optional — disables auth if unset
export DEX_STUDIO_HOST=0.0.0.0       # default
export DEX_STUDIO_PORT=7860          # default
```

Projects registry: `~/.dex-studio/projects.yaml`

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Server | FastAPI + Uvicorn |
| Templates | Jinja2 |
| Interactivity | HTMX |
| Engine | dataenginex (direct import) |
| Config | PyYAML + Pydantic |
| Build | Hatchling + uv |
| Testing | pytest + httpx TestClient |
| Linting | Ruff |
| Type Checking | mypy strict |

---

## Development

```bash
uv run poe lint          # ruff lint
uv run poe typecheck     # mypy strict
uv run poe test          # pytest
uv run poe check-all     # lint + typecheck + test
uv run poe dev           # uvicorn dev server (port 7860, reload)
```

---

**Version**: [![Release](https://img.shields.io/github/v/release/TheDataEngineX/dex-studio)](https://github.com/TheDataEngineX/dex-studio/releases) | **License**: MIT
