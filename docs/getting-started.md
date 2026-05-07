# Getting Started

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A running DEX engine (port 17000)

## Install

```bash
git clone https://github.com/TheDataEngineX/dex-studio.git
cd dex-studio
uv sync
```

## Run

Browser mode (development):

```bash
uv run poe dev
```

Native window mode:

```bash
uv run poe dev-native
```

Visit [http://localhost:7860](http://localhost:7860).

## Connect to DEX Engine

DEX Studio connects to a running DEX engine via HTTP. Start the engine first:

```bash
# In the DEX repo
uv run poe dev
```

Then start Studio — it will auto-detect the engine at `http://localhost:17000`.
