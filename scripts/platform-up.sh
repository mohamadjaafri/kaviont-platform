#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly TARGET_DIR="${REPO_ROOT}/.runtime/prometheus-targets"
readonly KUBE_NODE="kaviont-local-control-plane"

cd "${REPO_ROOT}"

for command in docker kind kubectl make; do
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

if ! docker network inspect kind >/dev/null 2>&1; then
  echo "The kind Docker network was not found after local-up." >&2
  exit 1
fi

echo "==> Connecting Prometheus and Blackbox Exporter to the kind Docker network."
for service in prometheus blackbox-exporter; do
  container_id="$(docker compose --profile observability ps -q "${service}")"
  if [[ -z "${container_id}" ]]; then
    echo "Compose service ${service} is not running." >&2
    exit 1
  fi

  networks="$(docker inspect --format '{{json .NetworkSettings.Networks}}' "${container_id}")"
  if ! grep -q '"kind"' <<< "${networks}"; then
    docker network connect kind "${container_id}"
  fi
done

echo
echo "Kaviont local platform is ready."
echo "Kubernetes API: use 'make local-forward' then http://127.0.0.1:8081"
echo "Grafana:        http://127.0.0.1:3000"
echo "Prometheus:     http://127.0.0.1:9090/targets"
echo "Alertmanager:   http://127.0.0.1:9093"
echo "Mailpit:        http://127.0.0.1:8025"
echo
echo "Run 'make platform-status' to inspect Kubernetes resources and Prometheus targets."
