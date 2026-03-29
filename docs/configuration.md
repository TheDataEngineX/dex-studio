______________________________________________________________________

## title: Configuration description: DEX Studio configuration reference

# Configuration

DEX Studio uses a YAML config file for customization.

## Config File

Create `.dex-studio.yaml` in the project root:

```yaml
engine:
  url: "http://localhost:17000"
  timeout: 30

ui:
  port: 7860
  theme: "dark"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEX_ENGINE_URL` | `http://localhost:17000` | DEX engine URL |
| `DEX_STUDIO_PORT` | `7860` | UI port |
