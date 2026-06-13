# Getting Started

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

No separate engine server required. DEX Studio imports `dataenginex` directly as a Python library.

## Install

```bash
git clone https://github.com/TheDataEngineX/dex-studio.git
cd dex-studio
uv sync
```

## Run

```bash
DEX_CONFIG_PATH=/path/to/dex.yaml uv run poe dev
```

Visit [http://localhost:7860](http://localhost:7860).

## Docker

```bash
docker compose up
```

Visit [http://localhost:7860](http://localhost:7860).

## First Login

On first start, an API key is auto-generated, printed to the console, and saved to `~/.dex-studio/api.key`:

```text
┌─────────────────────────────────────────────────────────┐
│  DEX Studio — API key generated (shown once)            │
│  Key: <your-key>                                        │
│  Saved to: ~/.dex-studio/api.key                        │
│  Set DEX_STUDIO_API_KEY env var to override.            │
└─────────────────────────────────────────────────────────┘
```

Enter this key at the `/login` page. The key is valid until you delete or replace it.

To override (e.g. in Docker or CI):

```bash
DEX_STUDIO_API_KEY=mykey uv run poe dev
```

## Switch Projects

Use the sidebar project dropdown to switch between registered projects at runtime.

To pre-register projects, edit `~/.dex-studio/projects.yaml`:

```yaml
projects:
  careerdex: ~/projects/careerdex/dex.yaml
  moviedex: /data/pipelines/moviedex/dex.yaml
```

## Generating Demo Assets

To regenerate screenshots, the demo video, and the README GIF after UI changes:

```bash
# System prerequisites (one-time)
brew install ffmpeg           # macOS
sudo apt install ffmpeg       # Ubuntu/Debian
cargo install agg             # asciinema GIF exporter (requires Rust)

# Python dev deps
uv sync --all-groups
uv run playwright install chromium

# Screenshots only (~60s, no ffmpeg needed)
uv run poe screenshots

# Full demo video + screenshots (~10 min, requires ffmpeg + agg)
uv run poe demo
```

Outputs land in `docs/`. Commit them alongside the code change.
After generating `docs/demo-full.mp4`, upload it to YouTube and update the `PLACEHOLDER` URL in `README.md`.
