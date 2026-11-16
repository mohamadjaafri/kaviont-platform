# Runbook: local operations dashboard

Kaviont's local operations profile is an optional Docker Compose stack. It demonstrates request telemetry, synthetic availability checks, an SLO/error budget, process resource metrics, alert evaluation, local email notification, and distributed traces. It does not require Azure.

## Components

- hello-api: FastAPI service with OpenTelemetry request metrics and traces. It also exports process CPU and resident-memory gauges.
- OpenTelemetry Collector: receives OTLP over gRPC/HTTP, batches telemetry, exposes Prometheus metrics, and forwards traces to Tempo.
- Prometheus: scrapes the Collector and Blackbox Exporter, retains up to 30 days of local metrics, evaluates SLO recording rules, and fires alerts.
- Blackbox Exporter: probes the API readiness endpoint over HTTP.
- Tempo: local trace storage with a 24-hour retention policy.
- Grafana: provisioned Kaviont operations and financial-data dashboards.
- Alertmanager: groups and routes Prometheus alerts.
- Mailpit: catches SMTP alert emails in a local inbox; no external email is sent.

## Start

    make observability-up

Wait until the containers are running:

    docker compose --profile observability ps

## Open the interfaces

- Grafana dashboard: http://127.0.0.1:3000 (local default credentials: admin / admin)
- Prometheus: http://127.0.0.1:9090
- Prometheus alerts: http://127.0.0.1:9090/alerts
- Alertmanager: http://127.0.0.1:9093
- Mailpit inbox: http://127.0.0.1:8025
- Tempo: http://127.0.0.1:3200
- Blackbox Exporter: http://127.0.0.1:9115

The Grafana operations dashboard includes:
- Availability SLO over a rolling 30-day window (target 99.9%).
- Remaining error budget (0.1% request budget).
- Current 5xx ratio, request rate, p95 latency, and readiness status.
- API process CPU utilization and resident memory.
- Distributed request traces.

## Generate healthy traffic

    for i in $(seq 1 60); do
      curl -sS http://127.0.0.1:8080/ >/dev/null
      sleep 0.2
    done

Wait for the OTLP metric export and Prometheus scrape intervals, then refresh Grafana. New environments need time to accumulate a 30-day history; the SLO panel uses the data currently retained.

## Automatically retrieve real financial market data

The API starts a background poller as part of the FastAPI lifespan. It fetches the configured pair immediately during startup and then repeats the request every 60 seconds by default. The default pair is XBTUSD (Bitcoin/USD). No Kraken account or API key is required.

Check the poller's status:

    curl -sS http://127.0.0.1:8080/v1/market/kraken/status

The status endpoint reports whether polling is enabled, whether a snapshot exists, the last successful update, cache age, and whether the cached value is stale.

Read the cached ticker snapshot:

    curl -sS http://127.0.0.1:8080/v1/market/kraken/ticker

The ticker endpoint serves the latest successful in-memory snapshot. It does not make another request to Kraken. The response includes last price, bid, ask, 24-hour volume, high, low, retrieval time, cache age, and a stale flag. If the provider is unavailable during a refresh, the poller retains the last good snapshot and retries at the next interval. Before the first successful fetch, the ticker endpoint returns HTTP 503.

Configure the poller using environment variables:

- KRAKEN_POLLING_ENABLED: true or false (default true).
- KRAKEN_POLL_INTERVAL_SECONDS: polling interval in seconds (default 60; minimum 1).
- KRAKEN_MARKET_PAIR: Kraken market pair (default XBTUSD).

Docker Compose reads optional overrides from the shell environment. In Helm deployments, configure the marketData values in the chart. Every running API replica has its own poller and in-memory cache, so each replica polls once per interval. A future multi-replica production design can move polling into a dedicated singleton worker and distribute snapshots through shared storage.

Each successful or failed upstream call emits:
- A kraken.public_ticker span in Tempo.
- A financial.api.requests counter with provider, pair, and outcome attributes.
- A financial.api.request.duration histogram for external latency.

Open Grafana's **Kaviont - Financial Data Reliability** dashboard. It shows external request rate, provider error ratio, p95 latency, and request/latency trends by market pair. The dashboard populates automatically once the startup poll succeeds and telemetry has been scraped. In Tempo, filter for service hello-api and inspect the kraken.public_ticker span.

Kraken's public Spot REST endpoints are rate limited by IP. Kraken states that a frequency of one request per second or less remains within public limits. The 60-second default interval is deliberately conservative. Avoid setting an unnecessarily short interval.

## Trigger a controlled 5xx alert

The API exposes /__test__/error only when KAVIONT_ENV is local or test. The Compose observability profile sets KAVIONT_ENV=local. The endpoint does not exist in the production configuration.

Generate a short burst:

    for i in $(seq 1 40); do
      curl -sS -o /dev/null http://127.0.0.1:8080/__test__/error
    done

The 5xx alert requires a sustained error ratio above 5% and a minimum request rate. Wait for the rule's two-minute pending duration and Alertmanager's grouping delay. The notification appears in Mailpit at http://127.0.0.1:8025.

The readiness alert can be tested by temporarily stopping the API:

    docker compose --profile observability stop hello-api

Restart it afterward:

    docker compose --profile observability start hello-api

## Understand the SLO

The example availability objective is 99.9% over a rolling 30-day window. The error budget is therefore 0.1% of observed requests. The dashboard calculates the remaining budget from the ratio of 5xx responses to all instrumented HTTP requests.

This is a request-based availability example, not a contractual SLA. It does not yet exclude selected routes or define user journeys. The readiness probe is a separate synthetic health signal and is not used in the request-based SLO calculation.

## Stop

    make observability-down

This removes the containers and network but keeps named volumes by default. To delete local metrics, traces, Grafana state, and alert silences as well:

    docker compose --profile observability down --volumes --remove-orphans

## Boundaries

This is a local learning profile, not production monitoring. It uses local storage, no TLS, no authentication for Prometheus, Tempo, Alertmanager, Mailpit, or Blackbox Exporter, and a single Collector. Ports bind to localhost. Mailpit captures mail instead of relaying it externally. Do not expose these ports to an untrusted network.

The CPU and memory gauges describe the hello-api process, not every Docker container or the host. The profile does not mount the Docker socket. A production AKS implementation should use a properly secured infrastructure metrics pipeline and managed alert notification destinations.

Do not put credentials, request bodies, personal data, or secret values into span attributes or logs. The local fault-injection route is not registered in the production environment.
