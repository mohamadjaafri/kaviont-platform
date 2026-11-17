#!/usr/bin/env bash
set -Eeuo pipefail

readonly KUBE_CONTEXT="kind-kaviont-local"

echo "==> Docker Compose observability services"
docker compose --profile observability ps
adminer_container="$(docker compose --profile observability ps -q adminer)"
if [[ -z "${adminer_container}" ]]; then
  echo "Adminer is not running. Start it with 'make database-ui'."
else
  echo "Adminer UI: http://127.0.0.1:8085"
fi

echo
echo "==> Argo CD applications"
kubectl --context "${KUBE_CONTEXT}" get applications -n argocd

echo
echo "==> Kubernetes workload and telemetry collector"
kubectl --context "${KUBE_CONTEXT}" get pods,svc -n kaviont-local

echo
echo "==> Prometheus Kubernetes targets"
prometheus_container="$(docker compose --profile observability ps -q prometheus)"
if [[ -z "${prometheus_container}" ]]; then
  echo "Prometheus is not running. Start the integrated stack with 'make platform-up'." >&2
  exit 1
fi

if ! targets_json="$(curl --fail --silent --show-error --max-time 5 http://127.0.0.1:9090/api/v1/targets?state=active)"; then
  echo "Prometheus API is not reachable on http://127.0.0.1:9090." >&2
  exit 1
fi

python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if payload.get("status") != "success":
    print("Prometheus returned an unsuccessful API response.", file=sys.stderr)
    raise SystemExit(1)

targets = [
    target
    for target in payload.get("data", {}).get("activeTargets", [])
    if target.get("labels", {}).get("platform") == "kubernetes"
]
for target in targets:
    labels = target.get("labels", {})
    print(
        "{}: {} - {}".format(
            labels.get("job", "?"),
            target.get("health", "unknown"),
            target.get("scrapeUrl", "?"),
        )
    )

if len(targets) != 2:
    print(
        "Expected 2 Kubernetes targets but found {}. Check make platform-up and Prometheus file discovery.".format(len(targets)),
        file=sys.stderr,
    )
    raise SystemExit(1)

if any(target.get("health") != "up" for target in targets):
    print("One or more Kubernetes Prometheus targets are not UP.", file=sys.stderr)
    raise SystemExit(1)

postgres_targets = [
    target for target in payload.get("data", {}).get("activeTargets", [])
    if target.get("labels", {}).get("job") == "postgres-exporter"
]
if len(postgres_targets) != 1 or postgres_targets[0].get("health") != "up":
    print("Expected one healthy postgres-exporter Prometheus target.", file=sys.stderr)
    raise SystemExit(1)
print("postgres-exporter: up - {}".format(postgres_targets[0].get("scrapeUrl", "?")))
' <<< "${targets_json}"

if ! pg_up_json="$(curl --fail --silent --show-error --max-time 5 --get --data-urlencode 'query=pg_up{job="postgres-exporter"}' http://127.0.0.1:9090/api/v1/query)"; then
  echo "Could not query PostgreSQL exporter health from Prometheus." >&2
  exit 1
fi

python3 -c '
import json
import sys
result = json.load(sys.stdin).get("data", {}).get("result", [])
if len(result) != 1 or result[0].get("value", [None, None])[1] != "1":
    print("PostgreSQL exporter is reachable but pg_up is not 1.", file=sys.stderr)
    raise SystemExit(1)
print("PostgreSQL database connection: healthy (pg_up=1)")
' <<< "${pg_up_json}"

echo
echo "Kaviont local platform checks passed."
