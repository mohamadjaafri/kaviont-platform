# Runbook: local observability

Kaviont's observability stack is an optional Docker Compose profile. It does not start during the normal API development loop and does not require Azure.

## Components

- OpenTelemetry SDK and FastAPI instrumentation: creates request traces and HTTP server metrics.
- OpenTelemetry Collector: receives OTLP over gRPC/HTTP, batches telemetry, exports metrics for Prometheus and traces to Tempo.
- Prometheus: scrapes the Collector's Prometheus exporter.
- Tempo: stores local traces for 24 hours.
- Grafana: provisions Prometheus and Tempo data sources and the hello-api dashboard.

## Start

```bash
make observability-up
```

The observability profile starts the API with OTLP enabled. The API remains available at http://127.0.0.1:8080.

Open:
- Grafana: http://127.0.0.1:3000 (local default credentials are admin / admin; change them if you expose Grafana beyond localhost).
- Prometheus: http://127.0.0.1:9090
- Tempo: http://127.0.0.1:3200

Grafana's pre-provisioned dashboard is named **Kaviont - Hello API**.

## Generate telemetry

```bash
for i in $(seq 1 50); do
  curl -sS http://127.0.0.1:8080/ >/dev/null
  curl -sS http://127.0.0.1:8080/healthz >/dev/null
done
```

In Grafana, inspect request rate, p95 HTTP latency, 5xx ratio, and recent traces. Metric names may vary slightly with OpenTelemetry semantic-convention versions; use Prometheus Explore to inspect `kaviont_*` if a panel has no data.

## Stop

```bash
make observability-down
```

Compose removes the containers and default network. Local telemetry storage is disposable. The normal `make dev-up` profile does not enable telemetry export.

## Boundaries

This is a local learning profile, not production monitoring. It uses local storage, default Grafana credentials, no TLS, no authentication for Prometheus/Tempo, and a single Collector. It exports no telemetry to a third party. Do not put credentials, request bodies, personal data, or secret values into span attributes or logs. Azure managed monitoring and AKS Collector deployment are future integration work.
