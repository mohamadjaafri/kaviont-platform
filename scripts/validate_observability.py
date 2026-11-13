#!/usr/bin/env python3
"""Validate the optional local observability configuration."""

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
        if not any(job.get("job_name") == "otel-collector" for job in prometheus["scrape_configs"]):
            raise ValueError("Prometheus must scrape the OpenTelemetry Collector")
        if tempo.get("storage", {}).get("trace", {}).get("backend") != "local":
            raise ValueError("Local Tempo must use local storage")
        if dashboard.get("uid") != "kaviont-hello-api":
            raise ValueError("Grafana dashboard UID is missing or unexpected")
        panel_titles = {panel.get("title") for panel in dashboard.get("panels", [])}
        required = {"HTTP request rate", "HTTP latency p95", "HTTP 5xx error ratio"}
        if not required.issubset(panel_titles):
            raise ValueError("Grafana dashboard is missing required HTTP panels")

        services = compose.get("services", {})
        for name in ("otel-collector", "prometheus", "tempo", "grafana"):
            service = services.get(name)
            if not service or "observability" not in service.get("profiles", []):
                raise ValueError(f"{name} must be restricted to the observability profile")
        api_profiles = services["hello-api"].get("profiles", [])
        if "dev" not in api_profiles or "observability" not in api_profiles:
            raise ValueError("hello-api must support both dev and observability profiles")

    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Observability validation failed: {exc}", file=sys.stderr)
        return 1

    print("OpenTelemetry Collector, Prometheus, Tempo, Grafana, dashboard, and Compose profile are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
