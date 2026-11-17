#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly TARGET_DIR="${REPO_ROOT}/.runtime/prometheus-targets"

cd "${REPO_ROOT}"

for command in docker kind kubectl make curl python3; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "${command} is required but was not found on PATH." >&2
    exit 1
  fi
done

docker info >/dev/null

echo "==> Starting the local kind cluster, Argo CD, API, and in-cluster OTel Collector."
bash "${SCRIPT_DIR}/local-up.sh"

echo "==> Configuring Prometheus discovery for the Kubernetes workload."
mkdir -p "${TARGET_DIR}"
cat > "${TARGET_DIR}/kubernetes-readiness.yml" <<'YAML'
- targets:
    - http://kaviont-local-control-plane:30081/readyz
  labels:
    probe: readiness
    platform: kubernetes
    environment: kind
YAML

cat > "${TARGET_DIR}/kubernetes-otel.yml" <<'YAML'
- targets:
    - kaviont-local-control-plane:30089
  labels:
    platform: kubernetes
    environment: kind
YAML

echo "==> Starting the Docker Compose observability stack."
make observability-up

echo "==> Ensuring Compose observability containers are connected to the kind Docker network."
make observability-connect-kind

echo "==> Waiting for Prometheus to scrape the Kubernetes Collector and readiness probe."
targets_ready=false
for attempt in $(seq 1 30); do
  if curl --fail --silent "http://127.0.0.1:9090/api/v1/targets?state=active" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin)["data"]["activeTargets"]; targets=[t for t in data if t["labels"].get("platform") == "kubernetes"]; sys.exit(0 if len(targets) == 2 and all(t["health"] == "up" for t in targets) else 1)'; then
    targets_ready=true
    break
  fi
  sleep 2
done

if [[ "${targets_ready}" != "true" ]]; then
  echo "Prometheus could not confirm both Kubernetes targets. Inspect make platform-status and Docker network connectivity." >&2
  exit 1
fi

echo "==> Waiting for postgres_exporter to report a healthy database connection."
postgres_ready=false
for attempt in $(seq 1 30); do
  if curl --fail --silent --get --data-urlencode 'query=pg_up{job="postgres-exporter"}' \
      http://127.0.0.1:9090/api/v1/query \
    | python3 -c 'import json,sys; result=json.load(sys.stdin)["data"]["result"]; sys.exit(0 if len(result) == 1 and result[0]["value"][1] == "1" else 1)'; then
    postgres_ready=true
    break
  fi
  sleep 2
done

if [[ "${postgres_ready}" != "true" ]]; then
  echo "postgres_exporter did not report pg_up=1. Inspect its role bootstrap and logs:" >&2
  docker compose --profile observability logs --no-color postgres-exporter-bootstrap postgres-exporter >&2 || true
  exit 1
fi

echo
echo "Kaviont local platform is ready."
echo "Kubernetes API: use 'make local-forward' then http://127.0.0.1:8081"
echo "Grafana:        http://127.0.0.1:3000"
echo "Prometheus:     http://127.0.0.1:9090/targets"
echo "Alertmanager:   http://127.0.0.1:9093"
echo "Mailpit:        http://127.0.0.1:8025"
echo "Adminer:        http://127.0.0.1:8085"
echo "PostgreSQL:     monitored by postgres_exporter (Grafana dashboard: Kaviont - PostgreSQL Reliability)"
echo
echo "Run 'make platform-status' to inspect Kubernetes resources and Prometheus targets."
