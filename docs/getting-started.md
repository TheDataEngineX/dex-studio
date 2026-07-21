# Getting Started

## Prerequisites

- Python 3.13+ and [uv](https://docs.astral.sh/uv/), or Docker
- [Ollama](https://ollama.com) (optional — for local LLM features)

No separate engine server. DEX Studio imports `dataenginex` directly.

## 1. Run

```bash
docker compose up
# open http://localhost:7860
```

Or natively:

```bash
git clone https://github.com/TheDataEngineX/dex-studio.git
cd dex-studio
uv sync
uv run poe dev
```

## 2. Login

First visit → `/setup` page → choose a password (min 8 chars). PBKDF2-hashed, saved to `~/.dex-studio/auth.hash`.

Log in at `/login` with that password.

## 3. Create a project

Click **New Project** in the sidebar. Give it a name and path — Studio creates a skeleton `dex.yaml` for you.

Or point at an existing config:

```bash
DEX_CONFIG_PATH=/path/to/your/dex.yaml uv run poe dev
```

A minimal `dex.yaml`:

```yaml
store:
  path: .dex/store.duckdb

pipelines:
  - name: ingest_movies
    source:
      type: csv
      path: data/movies.csv
    destination: bronze.movies
    schedule: daily
```

## 4. Run your first pipeline

Go to **Data → Pipelines** in the sidebar. Click **Run** on your pipeline.

Watch the live status stream — Bronze tables appear in **Warehouse** as rows land.

## 5. Query your data

Go to **Data → SQL Console**. Run SQL against your warehouse:

```sql
SELECT * FROM bronze.movies LIMIT 10;
```

Or check data quality under **Data → Quality**.

## 6. Train a model (optional)

Go to **Intelligence → Models → Train**. Pick features from your Gold tables, select an algorithm (scikit-learn, XGBoost), start training. Track experiments in **Experiments**, serve predictions via **Predictions**, monitor drift in **Drift**.

## 7. Chat with an AI agent (optional)

Go to **Intelligence → Playground**. Pick a model (Ollama default, or configure OpenAI/Anthropic in `dex.yaml`). Ask questions about your data — agents can query the warehouse, search embeddings, and surface findings.

```yaml
# dex.yaml — AI config
ai:
  default_model: ollama/llama3.2
  embedding_model: ollama/nomic-embed-text
```

## Next steps

| Guide | What it covers |
|-------|----------------|
| [Configuration](configuration.md) | All `dex.yaml` options — sources, pipelines, ML, AI, backends |
| [Architecture Reference](architecture-review.md) | Request flow, auth, scheduler, deployment |
| [Design Document](design.md) | Why FastAPI + HTMX, project structure, roadmap |
| [dataenginex docs](https://github.com/TheDataEngineX/dataenginex) | Full pipeline and engine reference |
| [InfraDEX](https://github.com/TheDataEngineX/infradex) | Kubernetes + ArgoCD deployment |

## Docker / CI notes

To pre-set the password (non-interactive):

```bash
echo "my-secret" > ~/.dex-studio/auth.hash   # PBKDF2 will hash on first use
```

Project registry at `~/.dex-studio/projects.yaml`:

```yaml
- name: moviedex
  config_path: /path/to/moviedex/dex.yaml
- name: ecommerce
  config_path: /path/to/ecommerce/dex.yaml
```

## Links

- [GitHub](https://github.com/TheDataEngineX/dex-studio)
- [Website](https://thedataenginex.org)
- [Full Documentation](https://docs.thedataenginex.org)