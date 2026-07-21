# Grafana Dashboards

This folder contains ready-to-import Grafana dashboards for DataEngineX observability.

## Dashboards

- **DataEngineX Metrics**: Prometheus-based service metrics (latency, error rate, RPS, in-flight).
- **DataEngineX Logs**: Loki-based log exploration and error spikes.
- **DataEngineX Traces**: Tempo-based tracing overview and trace search.

## Import

### Automatic (docker compose)

Dashboards and datasources are auto-provisioned when using `docker compose -f docker-compose.yml up -d`. No manual import needed.

### Manual

1. Open Grafana → **Dashboards** → **New** → **Import**.
1. Upload the JSON from `monitoring/grafana/dashboards/`.
1. Select the correct datasource when prompted.

## Data Sources

Three datasources are auto-provisioned via `monitoring/grafana/provisioning/datasources/datasources.yml`:

| Datasource | URL | Purpose |
| --- | --- | --- |
| Prometheus | `http://prometheus:9090` | Metrics (default) |
| Loki | `http://loki:3100` | Logs |
| Tempo | `http://tempo:3200` | Distributed traces |

Tempo is configured with `tracesToLogsV2` linking so trace spans link directly to Loki log lines.

## Sending Traces

DataEngineX sends traces via OTLP to Tempo:

- **gRPC**: `http://localhost:4317`
- **HTTP**: `http://localhost:4318`

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` (or `4318` for HTTP) in your DataEngineX config.

## Notes

Dashboards use default labels from DataEngineX metrics and structured logs. If your labels differ, update the dashboard variables or panel queries.

### Container Alerts

Alert rules in `monitoring/alerts/container-alerts.yml` detect OOM kills, CPU
throttling, and memory pressure. Import into Prometheus to enable container-level
alerting.

### Logging

The docker-compose stack uses the `json-file` logging driver with
`{{.Name}}/{{.ImageID}}` tag for container identification.

### Prometheus Scrape Targets

Prometheus auto-scrapes `dex-studio` (service metrics) and `cadvisor` (container
metrics) via the scrape configs in `monitoring/prometheus.yml`.
