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

On first start, DEX Studio redirects to the `/setup` page where you choose a password (minimum 8 characters). The password is PBKDF2-hashed and saved to `~/.dex-studio/auth.hash`.

After setting a password, log in at `/login` with the same password.

To pre-configure (e.g. in Docker or CI):

```bash
uv run poe dev   # set password via the /setup page on first visit
```

## Switch Projects

Use the sidebar project dropdown to switch between registered projects at runtime.

To pre-register projects, edit `~/.dex-studio/projects.yaml`:

```yaml
- name: moviedex
  config_path: /path/to/movie-dex/dex.yaml
- name: ecommerce
  config_path: /path/to/ecommerce/dex.yaml
```

## Generating Demo Assets

To regenerate screenshots, the demo video, and the README GIF after UI changes:

```bash
# System prerequisites (one-time)
brew install ffmpeg           # macOS
sudo apt install ffmpeg       # Ubuntu/Debian

# Python dev deps
uv sync --all-groups
uv run playwright install chromium

# Screenshots only (~60s, no ffmpeg needed)
uv run poe screenshots

# Full demo video (~10 min, requires ffmpeg)
uv run python scripts/demo/record.py

# GIF from video (15s highlight clip)
ffmpeg -i docs/demo-full.mp4 -t 15 -vf "fps=10,scale=800:-1" docs/demo.gif
```

Outputs land in `docs/`. Commit them alongside the code change.
