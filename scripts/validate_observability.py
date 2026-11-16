#!/usr/bin/env python3
"""Validate the local OpenTelemetry, SLO, alerting, and dashboard configuration."""

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
        tempo = load_yaml(ROOT / "observability/tempo.yaml")
        dashboard = json.loads(
            (ROOT / "observability/grafana/dashboards/hello-api.json").read_text(encoding="utf-8")
        )
        compose = load_yaml(ROOT / "compose.yaml")

        pipelines = collector["service"]["pipelines"]
        if set(pipelines) != {"metrics", "traces"}:
            raise ValueError("Collector must define metrics and traces pipelines")
        if "prometheus" not in pipelines["metrics"]["exporters"]:
            raise ValueError("Metrics pipeline must export to Prometheus")
        if "otlp/tempo" not in pipelines["traces"]["exporters"]:
            raise ValueError("Traces pipeline must export to Tempo")

        scrape_configs = prometheus["scrape_configs"]
        job_names = {job.get("job_name") for job in scrape_configs}
        if not {"otel-collector", "hello-api-readiness"}.issubset(job_names):
            raise ValueError("Prometheus must scrape the Collector and API readiness probe")
        probe_job = next(job for job in scrape_configs if job.get("job_name") == "hello-api-readiness")
        if probe_job.get("metrics_path") != "/probe":
            raise ValueError("Readiness probe must use the Blackbox Exporter /probe endpoint")
        if not prometheus.get("alerting", {}).get("alertmanagers"):
            raise ValueError("Prometheus must send alerts to Alertmanager")
        if not prometheus.get("rule_files"):
            raise ValueError("Prometheus must load the SLO and alert rule files")

        if "http_2xx" not in blackbox.get("modules", {}):
            raise ValueError("Blackbox Exporter must define the http_2xx probe")
        if blackbox["modules"]["http_2xx"].get("prober") != "http":
            raise ValueError("Readiness probe must use the HTTP prober")

        receivers = alertmanager.get("receivers", [])
        if not any(receiver.get("email_configs") for receiver in receivers):
            raise ValueError("Alertmanager must route local alerts to an email receiver")
        if alertmanager.get("global", {}).get("smtp_smarthost") != "mailpit:1025":
            raise ValueError("Alertmanager SMTP must use the local Mailpit service")

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
            "API Process CPU",
            "API Process Memory · Resident Set",
            "Distributed Traces · hello-api",
        }
        if not required_panels.issubset(panel_titles):
            raise ValueError("Grafana operations dashboard is missing required panels")

        services = compose.get("services", {})
        required_services = {
            "otel-collector", "prometheus", "tempo", "grafana",
            "blackbox-exporter", "alertmanager", "mailpit",
        }
        for name in required_services:
            service = services.get(name)
            if not service or "observability" not in service.get("profiles", []):
                raise ValueError(f"{name} must be restricted to the observability profile")
        api_profiles = services["hello-api"].get("profiles", [])
        if "dev" not in api_profiles or "observability" not in api_profiles:
            raise ValueError("hello-api must support both dev and observability profiles")
        prometheus_command = " ".join(services["prometheus"].get("command", []))
        if "--storage.tsdb.retention.time=30d" not in prometheus_command:
            raise ValueError("Prometheus must retain enough data for the 30-day SLO")
        if not any("observability/rules" in str(mount) for mount in services["prometheus"].get("volumes", [])):
            raise ValueError("Prometheus rule files must be mounted into the container")

    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Observability validation failed: {exc}", file=sys.stderr)
        return 1

    print("OpenTelemetry, SLO rules, Blackbox probes, Alertmanager, Mailpit, and Grafana dashboard are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
