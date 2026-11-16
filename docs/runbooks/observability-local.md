# Runbook: local operations dashboard

Kaviont's local operations profile is an optional Docker Compose stack. It demonstrates request telemetry, synthetic availability checks, an SLO/error budget, process resource metrics, alert evaluation, local email notification, and distributed traces. It does not require Azure.

## Components

- hello-api: stateless FastAPI service. It reads the latest market-data snapshot from PostgreSQL and exports request metrics, traces, CPU, and memory gauges.
- market-data-worker: separate polling process with its own OpenTelemetry service identity. It exports outbound Kraken spans and persists snapshots and worker state.
- PostgreSQL: persistent local storage for ticker history and worker heartbeats. A session-level advisory lock prevents overlapping workers.
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

## Automatically retrieve and persist real financial market data

The market-data worker runs as a dedicated Compose service, separate from FastAPI. It connects to PostgreSQL, acquires a session-level advisory lock, fetches the configured Kraken public ticker immediately, and repeats the request every 60 seconds by default. No Kraken account or API key is required.

Check the worker's persisted status:

    curl -sS http://127.0.0.1:8080/v1/market/kraken/status

The status endpoint reports whether the worker heartbeat is healthy, whether a successful snapshot exists, the last attempt, the last successful update, the last error category, and the worker instance identifier.

Read the latest database-backed ticker snapshot:

    curl -sS http://127.0.0.1:8080/v1/market/kraken/ticker

The API reads the latest persisted row. It does not contact Kraken. The response includes last price, bid, ask, 24-hour volume, high, low, Kaviont fetch time, cache age, and a stale flag. The fetch timestamp is the time Kaviont retrieved the response, not an exchange-provided event timestamp. If Kraken is unavailable during a refresh, the worker retains the last good snapshot and records a safe error category. Before the first successful fetch, the endpoint returns HTTP 503.

PostgreSQL uses a named Docker volume called market-data-db, so ticker history survives normal container restarts and `make observability-down`. The schema is initialized from db/init/001_market_data.sql when PostgreSQL creates a new data directory. Removing the volume with `docker compose --profile observability down --volumes` deletes the stored market history as well.

Configure the interval with KRAKEN_POLL_INTERVAL_SECONDS (default 60; minimum 1) and the pair with KRAKEN_MARKET_PAIR (default XBTUSD). Set POSTGRES_PASSWORD to override the local development database password. Do not reuse the sample default outside a local environment.

A second worker process cannot poll concurrently while the first holds the PostgreSQL advisory lock. During restart or deployment overlap, the second worker waits and retries lock acquisition. PostgreSQL is shared by every API replica, so scaling hello-api does not multiply external Kraken traffic.

Each successful or failed upstream call emits:
- A kraken.public_ticker span in Tempo with service.name=market-data-worker.
- A financial.api.requests counter with provider, pair, and outcome attributes.
- A financial.api.request.duration histogram for external latency.

Open Grafana's **Kaviont - Financial Data Reliability** dashboard. It shows external request rate, provider error ratio, p95 latency, and request/latency trends by market pair. In Tempo, filter for service market-data-worker and inspect the kraken.public_ticker span.

The v0.8 Helm chart contains an optional singleton worker Deployment and reads DATABASE_URL from an existing Kubernetes Secret. Both marketData.enabled and marketData.worker.enabled remain false in the AKS values template until an externally managed PostgreSQL database and its schema are available. The Terraform environment does not create or incur costs for a database in this release.

Kraken's public Spot REST endpoints are rate limited by IP. The 60-second default interval is deliberately conservative. Avoid setting an unnecessarily short interval.

## Historical market-data API

The v0.9 API exposes the historical ticker snapshots already collected by the worker. It does not fetch additional data from Kraken when a client requests history.

List the latest stored snapshot for each pair:

    curl -sS http://127.0.0.1:8080/v1/market/kraken/tickers | python3 -m json.tool

Read a 24-hour history for XBTUSD:

    curl -sS "http://127.0.0.1:8080/v1/market/kraken/history?pair=XBTUSD&range=24h&limit=500" | python3 -m json.tool

Supported ranges are 1h, 24h, and 7d. The limit accepts 2 to 2,000 points and defaults to 500. If the selected period contains more records than the limit, PostgreSQL distributes the returned points across the complete time window. Results stay chronological and include the total number of stored observations and whether downsampling occurred.

Read the calculated market summary:

    curl -sS "http://127.0.0.1:8080/v1/market/kraken/summary?pair=XBTUSD&range=24h" | python3 -m json.tool

The summary contains the first and latest recorded prices, absolute and percentage change between those observations, minimum and maximum observed last price, average last price, sample count, and first/last fetch timestamps. High, low, and average are calculated from Kaviont's stored last-price observations in the selected window, not exchange-provided OHLC candles. Price changes compare the first and last observations actually stored within the selected window. They are not a comparison with an exact candle open at the window boundary.

When a pair has no stored observations in the selected range, the history endpoint returns an empty data array and the summary returns a sample_count of zero with null price statistics. An unsupported range, invalid pair, or limit outside the supported bounds returns HTTP 422.

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
