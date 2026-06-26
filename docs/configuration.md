# Configuration

DEX Studio is configured entirely via environment variables. There is no `.dex-studio.yaml` config file.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEX_CONFIG_PATH` | — | Absolute path to the project's `dex.yaml` (required to auto-load an engine on startup) |
| `DEX_STUDIO_SESSION_SECRET` | auto | Secret used to sign session cookies. Auto-generated and saved to `~/.dex-studio/session.key` |
| `DEX_STUDIO_HOST` | `0.0.0.0` | Bind host |
| `DEX_STUDIO_PORT` | `7860` | Bind port |
| `DEX_HTTPS` | unset | Set to `1` to enable HTTPS-only session cookies |

## Projects Registry

`~/.dex-studio/projects.yaml` maps project names to `dex.yaml` paths. Used by the sidebar project switcher.

```yaml
projects:
  careerdex: ~/projects/careerdex/dex.yaml
  moviedex: /data/pipelines/moviedex/dex.yaml
```

Paths support `~` expansion. The file is created automatically when you add a project via the UI.

## CLI Flags

```bash
dex-studio                    # bind 0.0.0.0:7860
dex-studio --port 8080        # custom port
dex-studio --host 127.0.0.1  # localhost only
dex-studio --reload           # dev mode with auto-reload
dex-studio --version          # print version and exit
```

`DEX_CONFIG_PATH` must be set as an environment variable — there is no `--config` CLI flag.
