# DEX Studio

[![CI](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/TheDataEngineX/dex-studio/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**DEX Studio** is a local, Python-first UI that provides a single control plane for
end-to-end data projects powered by [TheDataEngineX/DEX](https://github.com/TheDataEngineX/DEX).

It connects to a running DEX engine instance and unifies workflows in one desktop window:
project setup → ingestion → medallion pipelines (bronze/silver/gold) → ML/AI workflows →
serving → observability.

______________________________________________________________________

## Quick Start

```bash
# Install
git clone https://github.com/TheDataEngineX/dex-studio && cd dex-studio
uv sync

# Start DEX engine first (in the DEX repo)
cd ../DEX && uv run poe dev

# Launch Studio (opens native window)
cd ../dex-studio && uv run dex-studio
```

### CLI Options

```bash
dex-studio                             # defaults (http://localhost:8000)
dex-studio --url http://host:8000      # custom DEX engine URL
dex-studio --token my-jwt-token        # authenticated connection
dex-studio --theme light               # light mode
dex-studio --config path/to/config.yaml
dex-studio --version
```

______________________________________________________________________

## Pages

| Page | Route | Description |
|---------------|-------------|-----------------------------------------------|
| Overview | `/` | System health, quality metrics, config |
| Health | `/health` | Liveness, readiness, startup probes |
| Data Quality | `/quality` | Medallion layer scores, source registry |
| Lineage | `/lineage` | Data lineage event explorer |
| ML Models | `/models` | Model registry, metadata, prediction playground |
| Settings | `/settings` | Connection config, theme preferences |

______________________________________________________________________

## Configuration

Config is loaded with this priority (highest wins):

1. CLI arguments
1. Environment variables (`DEX_STUDIO_API_URL`, `DEX_STUDIO_API_TOKEN`, …)
1. Project-local `.dex-studio.yaml`
1. User-level `~/.dex-studio/config.yaml`
1. Built-in defaults

```yaml
# ~/.dex-studio/config.yaml
api_url: "http://localhost:8000"
timeout: 10.0
theme: dark
poll_interval: 5.0
```

______________________________________________________________________

## Tech Stack

| Component | Technology |
|------------------|--------------------------------|
| UI Framework | NiceGUI + pywebview (native) |
| HTTP Client | httpx (async) |
| Config | PyYAML + Pydantic |
| Build | Hatchling + uv |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Type Checking | mypy (strict) |

______________________________________________________________________

## Development

```bash
git clone https://github.com/TheDataEngineX/dex-studio && cd dex-studio
uv run poe setup             # install all deps (including dev)

uv run poe lint              # ruff lint
uv run poe typecheck         # mypy strict
uv run poe test              # pytest
uv run poe check-all         # lint + typecheck + test
```

______________________________________________________________________

## Relationship to DEX

DEX Studio is a **separate project** that talks to DEX engine over HTTP.
It does not fork, embed, or rebrand upstream DEX.

- DEX engine provides the API, data pipelines, and ML infrastructure
- DEX Studio provides the unified UI to visualise and control those systems

Both repos are developed in **lockstep**: each Studio page drives a corresponding
DEX engine API endpoint. No Studio page without an API. No API without a Studio page.

______________________________________________________________________

**Version**: v0.1.0 | **License**: MIT
