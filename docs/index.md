# DEX Studio

**Open-source, self-hosted, local-first Data + ML + AI workbench.** Single-page web UI — no separate API server, no microservices.

## Features

- **Data** — Sources (CSV, Parquet, Postgres, Spark, dbt), Pipelines, SQL console, Warehouse (bronze/silver/gold), Lineage graph, Quality checks, Catalog, Transforms, Streaming, Schema, Backfill
- **Intelligence** — Playground (SSE streaming chat), Models, Experiments, Dashboard, Agents, Traces, Drift, Embeddings, Features, Predictions, Tools, Finetune
- **SecOps** — PrivacyGuard overview, PII strategy config, Audit log, Alert rules, Policies
- **System** — Status, Live log tail (SSE), Metrics, Runs feed, Scheduler, Compaction, Alerting, Costs, Components

## Quick Links

- [Getting Started](getting-started.md) — Install and run DEX Studio
- [Configuration](configuration.md) — Environment variables and CLI reference
- [Design](design.md) — Architecture and design decisions
- [Architecture Review](architecture-review.md) — Request lifecycle, auth, engine

## Run in 60 seconds

```bash
git clone https://github.com/TheDataEngineX/dex-studio
cd dex-studio
docker compose up
# open http://localhost:7860
```

______________________________________________________________________

See the [README](../README.md) for full details on configuration, tech stack, and development commands.
