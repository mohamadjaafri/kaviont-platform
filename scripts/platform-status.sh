#!/usr/bin/env bash
set -Eeuo pipefail

readonly KUBE_CONTEXT="kind-kaviont-local"

echo "==> Docker Compose observability services"
docker compose --profile observability ps

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
' <<< "${targets_json}"

echo
echo "Kaviont local platform checks passed."
