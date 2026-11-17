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
curl --fail --silent http://127.0.0.1:9090/api/v1/targets?state=active \
  | python3 -c 'import json,sys; data=json.load(sys.stdin)["data"]["activeTargets"]; targets=[t for t in data if t["labels"].get("platform") == "kubernetes"]; [print("{}: {} - {}".format(t["labels"].get("job", "?"), t["health"], t["scrapeUrl"])) for t in targets]; sys.exit(0 if len(targets) == 2 and all(t["health"] == "up" for t in targets) else 1)'

curl --fail --silent 'http://127.0.0.1:9090/api/v1/query?query=probe_success%7Bplatform%3D%22kubernetes%22%2Cprobe%3D%22readiness%22%7D' \
  | python3 -c 'import json,sys; results=json.load(sys.stdin)["data"]["result"]; value=float(results[0]["value"][1]) if results else 0; print("Kubernetes API readiness: " + ("UP" if value == 1 else "DOWN")); sys.exit(0 if value == 1 else 1)'
