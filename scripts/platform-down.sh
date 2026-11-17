#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly TARGET_DIR="${REPO_ROOT}/.runtime/prometheus-targets"

cd "${REPO_ROOT}"

echo "==> Stopping the Docker Compose observability stack (named volumes are retained)."
docker compose --profile observability down --remove-orphans

echo "==> Deleting the Kaviont kind cluster."
bash "${SCRIPT_DIR}/local-down.sh"

mkdir -p "${TARGET_DIR}"
printf '[]\n' > "${TARGET_DIR}/kubernetes-readiness.yml"
printf '[]\n' > "${TARGET_DIR}/kubernetes-otel.yml"

echo "Kaviont local platform stopped. Persistent Compose volumes were retained."
