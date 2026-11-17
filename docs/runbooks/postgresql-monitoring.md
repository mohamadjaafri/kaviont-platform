# PostgreSQL Monitoring Runbook

## Components

- PostgreSQL 17.5 is the monitored database.
- `prometheuscommunity/postgres-exporter:v0.20.1` exports PostgreSQL server statistics on port 9187 inside the Compose network.
- Prometheus scrapes `postgres-exporter:9187`.
- Grafana provisions the **Kaviont - PostgreSQL Reliability** dashboard.
- Adminer remains available at http://127.0.0.1:8085.

The exporter connects to the `postgres` maintenance database with a dedicated `postgres_exporter` account. The Compose bootstrap job creates or updates this account and grants the built-in `pg_monitor` role. It does not use the application's `kaviont` database login.

## Start and verify

Start the full local platform:

```bash
make platform-up
make platform-status
```

Start only PostgreSQL and the database UI:

```bash
make database-ui
```

Start the full observability stack independently:

```bash
make observability-up
```

The Compose dependency ensures the monitoring role bootstrap completes before the exporter starts. The bootstrap is idempotent and is safe to run against an existing named PostgreSQL volume.

## Credentials

The exporter password is separate from `POSTGRES_PASSWORD`. Set `POSTGRES_EXPORTER_PASSWORD` in the ignored local `.env` file to override the local default `kaviont-exporter-local-only`. Never commit a real local password.

The monitoring account has the PostgreSQL built-in `pg_monitor` role, which permits access to PostgreSQL monitoring views and settings. The exporter port is not published on the host.

## Verification

Open Prometheus targets:

- http://127.0.0.1:9090/targets

The `postgres-exporter` target should be `UP`. Check the database connection gauge in Prometheus:

```promql
pg_up{job="postgres-exporter"}
```

Expected value: `1`.

Useful queries:

```promql
sum(pg_stat_database_numbackends)
```

```promql
pg_database_size_bytes{datname="kaviont"}
```

```promql
sum(rate(pg_stat_database_xact_commit{datname="kaviont"}[5m]))
```

Open Grafana at http://127.0.0.1:3000 and select **Kaviont - PostgreSQL Reliability**.

## Alerts

| Alert | Meaning |
|---|---|
| `KaviontPostgreSQLExporterUnreachable` | Prometheus cannot scrape the exporter |
| `KaviontPostgreSQLUnavailable` | Exporter is running but cannot connect to PostgreSQL |
| `KaviontPostgreSQLConnectionsHigh` | Connection use exceeds 80% for 5 minutes |
| `KaviontPostgreSQLDeadlocksDetected` | At least one deadlock occurred in the last 5 minutes |
| `KaviontPostgreSQLLongRunningTransaction` | An active transaction has exceeded 5 minutes for 2 minutes |

Alerts are evaluated by Prometheus and routed through Alertmanager to the local Mailpit inbox.

## Troubleshooting

Inspect exporter and bootstrap logs:

```bash
docker compose --profile observability logs postgres-exporter-bootstrap postgres-exporter
```

Inspect the monitoring role:

```bash
docker compose exec postgres psql -U kaviont -d postgres -c "SELECT rolname, rolsuper, rolcanlogin FROM pg_roles WHERE rolname = 'postgres_exporter';"
```

The account should be non-superuser and able to log in. Verify its monitoring membership:

```bash
docker compose exec postgres psql -U kaviont -d postgres -c "SELECT pg_has_role('postgres_exporter', 'pg_monitor', 'member');"
```

If the password was changed in `.env`, rerun the bootstrap and recreate the exporter:

```bash
docker compose --profile observability rm -sf postgres-exporter-bootstrap postgres-exporter
docker compose --profile observability up -d postgres-exporter
```

The PostgreSQL named volume is not removed by these commands.
