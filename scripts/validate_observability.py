#!/usr/bin/env python3
"""Validate local OpenTelemetry, SLO, alerting, dashboard, and finance config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return value


def main() -> int:
    try:
        collector = load_yaml(ROOT / "observability/otel-collector-config.yaml")
        prometheus = load_yaml(ROOT / "observability/prometheus.yaml")
        blackbox = load_yaml(ROOT / "observability/blackbox.yaml")
        alertmanager = load_yaml(ROOT / "observability/alertmanager.yaml")
        rules = load_yaml(ROOT / "observability/rules/kaviont.yml")
        rule_test = load_yaml(ROOT / "observability/tests/kaviont-rules.test.yml")
        financial_rules = load_yaml(ROOT / "observability/rules/financial.yml")
        postgresql_rules = load_yaml(ROOT / "observability/rules/postgresql.yml")
        tempo = load_yaml(ROOT / "observability/tempo.yaml")
        dashboard = json.loads(
            (ROOT / "observability/grafana/dashboards/hello-api.json").read_text(encoding="utf-8")
        )
        financial_dashboard = json.loads(
            (ROOT / "observability/grafana/dashboards/financial-market.json").read_text(encoding="utf-8")
        )
        postgresql_dashboard = json.loads(
            (ROOT / "observability/grafana/dashboards/postgresql.json").read_text(encoding="utf-8")
        )
        compose = load_yaml(ROOT / "compose.yaml")

        pipelines = collector["service"]["pipelines"]
        trace_panels = [
            panel for panel in dashboard.get("panels", [])
            if panel.get("id") == 11 and panel.get("type") == "traces"
        ]
        if len(trace_panels) != 1:
            raise ValueError("Operations dashboard must contain exactly one distributed-traces panel")
        trace_targets = trace_panels[0].get("targets", [])
        if len(trace_targets) != 1 or trace_targets[0].get("query") != '{ resource.service.name =~ "hello-api(-kubernetes)?" }':
            raise ValueError("Distributed-traces panel must include both Compose and Kubernetes API services")
        if trace_panels[0].get("title") != "Distributed Traces · API Services":
            raise ValueError("Distributed-traces panel title must describe both API services")
        if set(pipelines) != {"metrics", "traces"}:
            raise ValueError("Collector must define metrics and traces pipelines")
        if "prometheus" not in pipelines["metrics"]["exporters"]:
            raise ValueError("Metrics pipeline must export to Prometheus")
        if "otlp/tempo" not in pipelines["traces"]["exporters"]:
            raise ValueError("Traces pipeline must export to Tempo")

        scrape_configs = prometheus["scrape_configs"]
        job_names = {job.get("job_name") for job in scrape_configs}
        if not {"otel-collector", "hello-api-readiness", "otel-collector-kubernetes", "hello-api-kubernetes-readiness", "postgres-exporter"}.issubset(job_names):
            raise ValueError("Prometheus must scrape Compose and Kubernetes telemetry, readiness, and PostgreSQL")
        postgres_job = next(job for job in scrape_configs if job.get("job_name") == "postgres-exporter")
        postgres_targets = [
            target
            for group in postgres_job.get("static_configs", [])
            for target in group.get("targets", [])
        ]
        if postgres_targets != ["postgres-exporter:9187"]:
            raise ValueError("Prometheus must scrape the internal postgres-exporter endpoint")
        kube_otel_job = next(job for job in scrape_configs if job.get("job_name") == "otel-collector-kubernetes")
        kube_readiness_job = next(job for job in scrape_configs if job.get("job_name") == "hello-api-kubernetes-readiness")
        if "/prometheus-targets/kubernetes-otel.yml" not in [
            file for group in kube_otel_job.get("file_sd_configs", []) for file in group.get("files", [])
        ]:
            raise ValueError("Kubernetes Collector must use a runtime file-discovery target")
        if "/prometheus-targets/kubernetes-readiness.yml" not in [
            file for group in kube_readiness_job.get("file_sd_configs", []) for file in group.get("files", [])
        ]:
            raise ValueError("Kubernetes readiness must use a runtime file-discovery target")
        if kube_readiness_job.get("metrics_path") != "/probe" or not any(
            item.get("replacement") == "blackbox-exporter:9115"
            for item in kube_readiness_job.get("relabel_configs", [])
        ):
            raise ValueError("Kubernetes readiness must be probed through the Blackbox Exporter")
        probe_job = next(job for job in scrape_configs if job.get("job_name") == "hello-api-readiness")
        if probe_job.get("metrics_path") != "/probe":
            raise ValueError("Readiness probe must use the Blackbox Exporter /probe endpoint")
        if not prometheus.get("alerting", {}).get("alertmanagers"):
            raise ValueError("Prometheus must send alerts to Alertmanager")
        if not prometheus.get("rule_files"):
            raise ValueError("Prometheus must load the SLO and alert rule files")
        if "/etc/prometheus/rules/*.yml" not in prometheus["rule_files"]:
            raise ValueError("Prometheus must load the financial recording rules")

        if "http_2xx" not in blackbox.get("modules", {}):
            raise ValueError("Blackbox Exporter must define the http_2xx probe")
        if blackbox["modules"]["http_2xx"].get("prober") != "http":
            raise ValueError("Readiness probe must use the HTTP prober")

        receivers = alertmanager.get("receivers", [])
        if not any(receiver.get("email_configs") for receiver in receivers):
            raise ValueError("Alertmanager must route local alerts to an email receiver")
        if alertmanager.get("global", {}).get("smtp_smarthost") != "mailpit:1025":
            raise ValueError("Alertmanager SMTP must use the local Mailpit service")
        if not alertmanager.get("global", {}).get("smtp_from"):
            raise ValueError("Alertmanager must define a sender address")

        receiver_names = {receiver.get("name") for receiver in receivers}
        if alertmanager.get("route", {}).get("receiver") not in receiver_names:
            raise ValueError("Alertmanager's default route must reference an existing receiver")
        email_configs = [
            config
            for receiver in receivers
            for config in receiver.get("email_configs", [])
        ]
        if not any(
            config.get("to") == "platform-ops@local.test"
            and config.get("send_resolved") is True
            for config in email_configs
        ):
            raise ValueError("Alertmanager must deliver firing and resolved notifications to the local operations inbox")

        groups = rules.get("groups", [])
        recording_names = {
            rule.get("record")
            for group in groups for rule in group.get("rules", [])
            if "record" in rule
        }
        alert_names = {
            rule.get("alert")
            for group in groups for rule in group.get("rules", [])
            if "alert" in rule
        }
        required_recordings = {
            "kaviont:http_requests:rate5m",
            "kaviont:http_errors:ratio5m",
            "kaviont:http_latency:p95_5m",
            "kaviont:slo:availability:ratio30d",
            "kaviont:slo:error_budget:remaining_ratio30d",
            "kaviont:slo:error_budget:burn_rate5m",
            "kaviont:slo:error_budget:burn_rate1h",
        }
        required_alerts = {
            "KaviontAPIReadinessProbeFailed",
            "KaviontAPIHighErrorRate",
            "KaviontAPIHighLatency",
            "KaviontSLOBurnRateCritical",
            "KaviontSLOErrorBudgetNearlyExhausted",
            "KaviontProcessCPUHigh",
            "KaviontProcessMemoryHigh",
        }
        if not required_recordings.issubset(recording_names):
            raise ValueError("SLO recording rules are incomplete")
        if not required_alerts.issubset(alert_names):
            raise ValueError("Operational alert rules are incomplete")
        postgresql_alert_names = {
            rule.get("alert")
            for group in postgresql_rules.get("groups", [])
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        required_postgresql_alerts = {
            "KaviontPostgreSQLExporterUnreachable",
            "KaviontPostgreSQLUnavailable",
            "KaviontPostgreSQLConnectionsHigh",
            "KaviontPostgreSQLDeadlocksDetected",
            "KaviontPostgreSQLLongRunningTransaction",
        }
        postgresql_recordings = {
            rule.get("record")
            for group in postgresql_rules.get("groups", [])
            for rule in group.get("rules", [])
            if "record" in rule
        }
        required_postgresql_recordings = {
            "kaviont:postgres_connections:count",
            "kaviont:postgres_connections:utilization",
            "kaviont:postgres_cache_hit_ratio:ratio5m",
            "kaviont:postgres_transactions:rate5m",
        }
        if not required_postgresql_alerts.issubset(postgresql_alert_names):
            raise ValueError("PostgreSQL alert rules are incomplete")
        if not required_postgresql_recordings.issubset(postgresql_recordings):
            raise ValueError("PostgreSQL recording rules are incomplete")
        postgresql_expressions = "\n".join(
            str(rule.get("expr", ""))
            for group in postgresql_rules.get("groups", [])
            for rule in group.get("rules", [])
        )
        for metric in (
            "pg_up",
            "pg_stat_database_numbackends",
            "pg_settings_max_connections",
            "pg_stat_database_blks_hit",
            "pg_stat_database_blks_read",
            "pg_stat_database_xact_commit",
            "pg_stat_database_xact_rollback",
            "pg_stat_database_deadlocks",
            "pg_stat_activity_max_tx_duration",
        ):
            if metric not in postgresql_expressions:
                raise ValueError(f"PostgreSQL rules must use exporter metric {metric}")

        rule_expressions = [
            str(rule.get("expr", ""))
            for group in groups
            for rule in group.get("rules", [])
        ]
        all_rule_expressions = "\n".join(rule_expressions)
        required_http_metrics = {
            "kaviont_http_server_duration_milliseconds_count",
            "kaviont_http_server_duration_milliseconds_bucket",
        }
        for metric_name in required_http_metrics:
            if metric_name not in all_rule_expressions:
                raise ValueError(f"HTTP SLO rules must use the exported metric {metric_name}")
        if 'http_status_code=~"5.."' not in all_rule_expressions:
            raise ValueError("HTTP error rules must filter the exported http_status_code label")
        if 'http_target!="/__test__/error"' not in all_rule_expressions:
            raise ValueError("HTTP SLO rules must exclude the local fault-injection route")
        obsolete_http_identifiers = (
            "kaviont_http_server_request_duration_seconds",
            "http_response_status_code",
        )
        if any(identifier in all_rule_expressions for identifier in obsolete_http_identifiers):
            raise ValueError("HTTP SLO rules contain obsolete OpenTelemetry metric or label names")
        if rule_test.get("rule_files") != ["../rules/kaviont.yml", "../rules/postgresql.yml"]:
            raise ValueError("Prometheus rule tests must include API and PostgreSQL rules")
        test_series = [
            str(series.get("series", ""))
            for test_group in rule_test.get("tests", [])
            for series in test_group.get("input_series", [])
        ]
        if not any('http_status_code="500"' in series for series in test_series):
            raise ValueError("Prometheus rule tests must include synthetic HTTP 500 traffic")
        if not any('http_status_code="200"' in series for series in test_series):
            raise ValueError("Prometheus rule tests must include healthy HTTP 200 traffic")
        if not any('http_target="/__test__/error"' in series for series in test_series):
            raise ValueError("Prometheus rule tests must cover the local fault-injection route")

        latency_alert = next(
            rule for group in groups for rule in group.get("rules", [])
            if rule.get("alert") == "KaviontAPIHighLatency"
        )
        if "kaviont:http_latency:p95_5m > 500" not in str(latency_alert.get("expr", "")):
            raise ValueError("The p95 alert threshold must use milliseconds (500 ms)")

        process_cpu_alert = next(
            rule for group in groups for rule in group.get("rules", [])
            if rule.get("alert") == "KaviontProcessCPUHigh"
        )
        process_memory_alert = next(
            rule for group in groups for rule in group.get("rules", [])
            if rule.get("alert") == "KaviontProcessMemoryHigh"
        )
        if 'process_name="hello-api"' not in str(process_cpu_alert.get("expr", "")):
            raise ValueError("API CPU alert must select the hello-api process")
        if 'process_name="hello-api"' not in str(process_memory_alert.get("expr", "")):
            raise ValueError("API memory alert must select the hello-api process")

        financial_recordings = {
            rule.get("record")
            for group in financial_rules.get("groups", [])
            for rule in group.get("rules", [])
            if "record" in rule
        }
        required_financial_recordings = {
            "kaviont:financial_api_requests:rate5m",
            "kaviont:financial_api_errors:ratio5m",
            "kaviont:financial_api_latency:p95_5m",
        }
        if not required_financial_recordings.issubset(financial_recordings):
            raise ValueError("Financial API recording rules are incomplete")

        if tempo.get("storage", {}).get("trace", {}).get("backend") != "local":
            raise ValueError("Local Tempo must use local storage")
        if dashboard.get("uid") != "kaviont-operations":
            raise ValueError("Grafana operations dashboard UID is missing or unexpected")
        panel_titles = {panel.get("title") for panel in dashboard.get("panels", [])}
        required_panels = {
            "Availability SLO · 30 days",
            "Error Budget Remaining",
            "HTTP 5xx Ratio · 5 min",
            "Latency · p95",
            "Request Rate",
            "Readiness Probe",
            "Kubernetes API Readiness",
            "Kubernetes API Request Rate",
            "Kubernetes API Latency · p95",
            "API Process CPU",
            "API Process Memory · Resident Set",
            "Distributed Traces · hello-api",
        }
        if not required_panels.issubset(panel_titles):
            raise ValueError("Grafana operations dashboard is missing required panels")
        process_cpu_panel = next(panel for panel in dashboard.get("panels", []) if panel.get("title") == "API Process CPU")
        process_memory_panel = next(panel for panel in dashboard.get("panels", []) if panel.get("title") == "API Process Memory · Resident Set")
        if 'process_name="hello-api"' not in process_cpu_panel.get("targets", [{}])[0].get("expr", ""):
            raise ValueError("Grafana API CPU panel must select the hello-api process")
        if 'process_name="hello-api"' not in process_memory_panel.get("targets", [{}])[0].get("expr", ""):
            raise ValueError("Grafana API memory panel must select the hello-api process")

        latency_panels = [
            panel for panel in dashboard.get("panels", [])
            if panel.get("title") == "Latency · p95"
        ]
        if len(latency_panels) != 2:
            raise ValueError("Grafana operations dashboard must expose both p95 latency panels")
        if any(
            panel.get("fieldConfig", {}).get("defaults", {}).get("unit") != "ms"
            for panel in latency_panels
        ):
            raise ValueError("Grafana p95 latency panels must display milliseconds")
        latency_stat = next(panel for panel in latency_panels if panel.get("type") == "stat")
        latency_thresholds = {
            step.get("value")
            for step in latency_stat.get("fieldConfig", {}).get("defaults", {})
                .get("thresholds", {}).get("steps", [])
        }
        if not {250, 500}.issubset(latency_thresholds):
            raise ValueError("Grafana p95 thresholds must match 250 ms and 500 ms")

        if financial_dashboard.get("uid") != "kaviont-financial-data":
            raise ValueError("Grafana financial dashboard UID is missing or unexpected")
        if postgresql_dashboard.get("uid") != "kaviont-postgresql":
            raise ValueError("Grafana PostgreSQL dashboard UID is missing or unexpected")
        postgresql_panel_titles = {
            panel.get("title") for panel in postgresql_dashboard.get("panels", [])
        }
        required_postgresql_panels = {
            "PostgreSQL Exporter Status",
            "Current Connections",
            "Connection Utilization",
            "Database Size",
            "Transactions per Second",
            "Buffer Cache Hit Ratio",
            "Connections by State",
            "Transaction Throughput",
            "Deadlocks · 5 min",
            "Longest Active Transaction",
            "Locks by Mode",
        }
        if not required_postgresql_panels.issubset(postgresql_panel_titles):
            raise ValueError("Grafana PostgreSQL dashboard is missing required panels")
        financial_panel_titles = {
            panel.get("title") for panel in financial_dashboard.get("panels", [])
        }
        required_financial_panels = {
            "External API Request Rate",
            "Kraken API Error Ratio",
            "Kraken API Latency · p95",
            "Requests by Market Pair and Outcome",
            "External API Latency · p95 by Pair",
        }
        if not required_financial_panels.issubset(financial_panel_titles):
            raise ValueError("Grafana financial dashboard is missing required panels")

        api_source = (ROOT / "workloads/hello-api/app/main.py").read_text(encoding="utf-8")
        worker_source = (ROOT / "workloads/hello-api/app/market_worker.py").read_text(encoding="utf-8")
        repository_source = (ROOT / "workloads/hello-api/app/market_repository.py").read_text(encoding="utf-8")
        schema_source = (ROOT / "db/init/001_market_data.sql").read_text(encoding="utf-8")
        financial_source = (ROOT / "workloads/hello-api/app/financial.py").read_text(encoding="utf-8")
        requirements = (ROOT / "workloads/hello-api/requirements.txt").read_text(encoding="utf-8")
        if "/v1/market/kraken/ticker" not in api_source:
            raise ValueError("FastAPI market-data endpoint is missing")
        if "/v1/market/kraken/status" not in api_source:
            raise ValueError("FastAPI market-data status endpoint is missing")
        for endpoint in (
            "/v1/market/kraken/tickers",
            "/v1/market/kraken/history",
            "/v1/market/kraken/summary",
        ):
            if endpoint not in api_source:
                raise ValueError(f"FastAPI market-data endpoint is missing: {endpoint}")
        for method in ("latest_tickers", "historical_ticker", "market_summary"):
            if f"def {method}(" not in repository_source:
                raise ValueError(f"PostgreSQL repository method is missing: {method}")
        if "KrakenTickerPoller" in api_source or "fetch_kraken_ticker" in api_source:
            raise ValueError("The API must not poll the external market-data provider")
        if "KRAKEN_POLL_INTERVAL_SECONDS" not in worker_source:
            raise ValueError("The standalone worker polling interval must be configurable")
        if "pg_try_advisory_lock" not in repository_source:
            raise ValueError("The worker must use a PostgreSQL advisory singleton lock")
        if "market_ticker_snapshots" not in schema_source or "market_data_worker_state" not in schema_source:
            raise ValueError("PostgreSQL schema must include snapshots and worker state")
        if "DATABASE_URL" not in repository_source:
            raise ValueError("The API must connect to shared market-data storage")
        if "https://api.kraken.com/0/public/Ticker" not in financial_source:
            raise ValueError("Kraken public ticker endpoint is missing")
        if "httpx>=" not in requirements:
            raise ValueError("The runtime image must install HTTPX")

        services = compose.get("services", {})
        required_services = {
            "otel-collector", "prometheus", "tempo", "grafana",
            "blackbox-exporter", "alertmanager", "mailpit",
            "postgres", "market-data-worker", "adminer",
            "postgres-exporter-bootstrap", "postgres-exporter",
        }
        for name in required_services:
            service = services.get(name)
            if not service or "observability" not in service.get("profiles", []):
                raise ValueError(f"{name} must be restricted to the observability profile")
        api_environment = services["hello-api"].get("environment", {})
        if "postgresql://" not in api_environment.get("DATABASE_URL", ""):
            raise ValueError("Compose API must read market data from PostgreSQL")
        worker_environment = services["market-data-worker"].get("environment", {})
        if worker_environment.get("OTEL_SERVICE_NAME") != "market-data-worker":
            raise ValueError("The market-data worker must have its own telemetry service name")
        if worker_environment.get("KRAKEN_POLL_INTERVAL_SECONDS") != "${KRAKEN_POLL_INTERVAL_SECONDS:-60}":
            raise ValueError("Compose worker polling interval must default to 60 seconds")
        if "postgresql://" not in worker_environment.get("DATABASE_URL", ""):
            raise ValueError("Compose worker must persist snapshots to PostgreSQL")
        if not any("db/init" in str(mount) for mount in services["postgres"].get("volumes", [])):
            raise ValueError("Compose PostgreSQL service must mount the initial schema")
        if services["postgres"].get("healthcheck") is None:
            raise ValueError("Compose PostgreSQL service must expose a health check")
        adminer_service = services["adminer"]
        if adminer_service.get("environment", {}).get("ADMINER_DEFAULT_SERVER") != "postgres":
            raise ValueError("Adminer must default to the Compose PostgreSQL service")
        if "127.0.0.1:8085:8080" not in {
            str(port) for port in adminer_service.get("ports", [])
        }:
            raise ValueError("Adminer must bind its web UI to localhost on port 8085")
        if adminer_service.get("depends_on", {}).get("postgres", {}).get("condition") != "service_healthy":
            raise ValueError("Adminer must wait for PostgreSQL to become healthy")
        bootstrap_service = services["postgres-exporter-bootstrap"]
        if bootstrap_service.get("entrypoint") != ["/bin/sh", "/scripts/bootstrap-postgres-exporter-role.sh"]:
            raise ValueError("PostgreSQL exporter role bootstrap must run the reviewed shell script")
        if bootstrap_service.get("depends_on", {}).get("postgres", {}).get("condition") != "service_healthy":
            raise ValueError("PostgreSQL exporter role bootstrap must wait for a healthy database")
        if not any("bootstrap-postgres-exporter-role.sh" in str(mount) for mount in bootstrap_service.get("volumes", [])):
            raise ValueError("PostgreSQL exporter role bootstrap script must be mounted read-only")
        bootstrap_environment = bootstrap_service.get("environment", {})
        if not str(bootstrap_environment.get("POSTGRES_EXPORTER_PASSWORD", "")).startswith("${POSTGRES_EXPORTER_PASSWORD:-"):
            raise ValueError("PostgreSQL exporter password must be configurable outside Git")
        exporter_service = services["postgres-exporter"]
        if exporter_service.get("image") != "prometheuscommunity/postgres-exporter:v0.20.1":
            raise ValueError("PostgreSQL exporter image must be pinned to the reviewed v0.20.1 release")
        exporter_environment = exporter_service.get("environment", {})
        if exporter_environment.get("DATA_SOURCE_URI") != "postgres:5432/postgres?sslmode=disable":
            raise ValueError("PostgreSQL exporter must use DATA_SOURCE_URI for the internal Compose PostgreSQL service")
        if "command" in exporter_service:
            raise ValueError("PostgreSQL exporter connection URI must be configured through the documented environment variable")
        if exporter_environment.get("DATA_SOURCE_USER") != "postgres_exporter":
            raise ValueError("PostgreSQL exporter must use its dedicated monitoring role")
        if exporter_service.get("depends_on", {}).get("postgres-exporter-bootstrap", {}).get("condition") != "service_completed_successfully":
            raise ValueError("PostgreSQL exporter must wait for its monitoring role bootstrap")
        if "9187" not in {str(port) for port in exporter_service.get("expose", [])} or exporter_service.get("ports"):
            raise ValueError("PostgreSQL exporter must expose metrics internally without publishing a host port")
        bootstrap_script = (ROOT / "scripts/bootstrap-postgres-exporter-role.sh").read_text(encoding="utf-8")
        if "GRANT pg_monitor TO postgres_exporter" not in bootstrap_script:
            raise ValueError("PostgreSQL exporter role must receive the built-in pg_monitor role")
        if "ALTER ROLE postgres_exporter WITH LOGIN PASSWORD" not in bootstrap_script:
            raise ValueError("PostgreSQL exporter role bootstrap must support idempotent password updates")
        mailpit_service = services.get("mailpit", {})
        if "1025" not in {str(port) for port in mailpit_service.get("expose", [])}:
            raise ValueError("Mailpit must expose its SMTP port to the Compose network")
        if "mailpit" not in services["alertmanager"].get("depends_on", []):
            raise ValueError("Alertmanager must start with the local Mailpit SMTP service available")
        api_profiles = services["hello-api"].get("profiles", [])
        if "dev" not in api_profiles or "observability" not in api_profiles:
            raise ValueError("hello-api must support both dev and observability profiles")
        prometheus_command = " ".join(services["prometheus"].get("command", []))
        if "--storage.tsdb.retention.time=30d" not in prometheus_command:
            raise ValueError("Prometheus must retain enough data for the 30-day SLO")
        if not any("observability/rules" in str(mount) for mount in services["prometheus"].get("volumes", [])):
            raise ValueError("Prometheus rule files must be mounted into the container")
        if not any(".runtime/prometheus-targets" in str(mount) for mount in services["prometheus"].get("volumes", [])):
            raise ValueError("Prometheus runtime Kubernetes target directory must be mounted")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ("platform-up:", "platform-down:", "platform-status:", "database-ui:", "database-ui-down:"):
            if target not in makefile:
                raise ValueError(f"Makefile is missing the integrated local platform target {target}")
        platform_up = (ROOT / "scripts/platform-up.sh").read_text(encoding="utf-8")
        for required in ("local-up.sh", "make observability-up", "make observability-connect-kind", "kubernetes-readiness.yml", "kubernetes-otel.yml", "pg_up"):
            if required not in platform_up:
                raise ValueError(f"Integrated platform startup is missing: {required}")
        network_helper = (ROOT / "scripts/connect-observability-to-kind.sh").read_text(encoding="utf-8")
        for required in ("docker network connect kind", "prometheus blackbox-exporter tempo", ".IPAddress", "otel-collector-runtime", "tempo_otlp_endpoint", "rollout restart deployment/otel-collector"):
            if required not in network_helper:
                raise ValueError(f"Observability network helper is missing Tempo integration behavior: {required}")
        if "$(MAKE) observability-connect-kind" not in makefile:
            raise ValueError("make observability-up must restore the kind network attachment after Compose recreation")
        platform_status = (ROOT / "scripts/platform-status.sh").read_text(encoding="utf-8")
        if "pg_up" not in platform_status or "postgres-exporter" not in platform_status:
            raise ValueError("Platform status must validate PostgreSQL exporter and database health")

    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Observability validation failed: {exc}", file=sys.stderr)
        return 1

    print("OpenTelemetry, SLO rules, market-data worker, PostgreSQL storage, and Grafana dashboards are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
