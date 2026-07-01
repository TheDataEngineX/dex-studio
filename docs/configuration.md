# Configuration

DEX Studio is configured entirely via environment variables. There is no `.dex-studio.yaml` config file.

## Environment Variables

### Required

| Variable | Description |
| --- | --- |
| `DEX_STUDIO_SESSION_SECRET` | Secret used to sign session cookies. Generate: `python -c "import secrets; print(secrets.token_hex(32))"`. Auto-generated and saved to `~/.dex-studio/session.key` if not set. |

### Optional

| Variable | Default | Description |
| --- | --- | --- |
| `DEX_CONFIG_PATH` | — | Absolute path to the project's `dex.yaml`. When set, the engine is auto-loaded on startup. Otherwise uses the saved default project from the projects registry. |
| `DEX_STUDIO_PASSPHRASE` | — | Pre-set admin password. When set, bypasses the `/setup` first-boot UI flow. Minimum 8 characters. |
| `DEX_HTTPS` | `false` | Set to `1`, `true`, or `yes` to enable HTTPS-only (`Secure`) session cookies and the `Strict-Transport-Security` header. |
| `DEX_TRUSTED_PROXIES` | `0` | Number of trusted reverse-proxy hops for client IP extraction (used by the login rate limiter). Set to `1` when behind a single proxy (e.g. nginx, Traefik). |
| `DATABASE_URL` | — | PostgreSQL connection string (`postgresql+psycopg://user:pass@host:5432/db`). When set, enables multi-pod mode: scheduler state, pipeline locks, and project registry are stored in Postgres instead of local SQLite/files. |

### Bind / Server

| Variable | Default | Description |
| --- | --- | --- |
| `DEX_STUDIO_HOST` | `0.0.0.0` | Bind host |
| `DEX_STUDIO_PORT` | `7860` | Bind port |

## Projects Registry

`~/.dex-studio/projects.yaml` is a list of registered projects used by the sidebar project switcher.

```yaml
- name: moviedex
  config_path: /path/to/movie-dex/dex.yaml
- name: ecommerce
  config_path: /path/to/ecommerce/dex.yaml
```

The file is created automatically when you add a project via the UI. Edit it directly to pre-register projects.

## CLI Flags

```bash
dex-studio                    # bind 0.0.0.0:7860
dex-studio --port 8080        # custom port
dex-studio --host 127.0.0.1  # localhost only
dex-studio --reload           # dev mode with auto-reload
dex-studio --version          # print version and exit
```

`DEX_CONFIG_PATH` must be set as an environment variable — there is no `--config` CLI flag.
