# ADR 0005: separate market-data polling from the API

- Status: accepted
- Date: 2026-11-16

## Context

The v0.7 implementation started a Kraken polling loop inside every FastAPI process. That design coupled the API lifecycle to external polling and kept the most recent ticker in process memory. Scaling the API to multiple replicas therefore created multiple independent pollers and inconsistent snapshots.

## Decision

Move provider polling into a dedicated market-data-worker process. Store each successful snapshot and worker health state in PostgreSQL. The API reads the latest snapshot from PostgreSQL and does not call the external provider.

The worker holds a PostgreSQL session-level advisory lock for its lifetime. The lock prevents simultaneous poll loops during overlapping deployments or accidental duplicate worker replicas. The Helm chart uses a single-replica Deployment with the Recreate strategy as an additional operational guard, while the database lock remains the coordination mechanism.

The local Compose profile runs PostgreSQL, hello-api, and market-data-worker. The schema is initialized from db/init/001_market_data.sql for a new local database volume. The Helm chart exposes optional worker and database-secret configuration but leaves both disabled until an AKS database is provisioned and migrated.

## Consequences

- API replicas share one consistent persisted snapshot and can scale independently.
- Historical ticker observations are retained for future history endpoints.
- Provider polling and API request availability have separate process boundaries.
- PostgreSQL becomes a runtime dependency for market-data endpoints.
- Local database data survives normal container restarts but is removed when the named volume is deleted.
- The AKS worker is not enabled by default because the current Terraform environment does not provision a PostgreSQL service.
- A future release should replace container init SQL with a versioned migration workflow and evaluate a connection pool for higher API concurrency.

## Alternatives considered

- Keep polling in FastAPI and force replicaCount to one: rejected because API availability and polling remain coupled, and deployment overlap can still duplicate requests.
- Add Redis only: rejected because the project needs durable ticker history, not only a shared cache.
- Introduce Kafka or a streaming platform: deferred because the current ingestion rate and data model do not justify the operational complexity.
