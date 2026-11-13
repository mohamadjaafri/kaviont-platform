#!/usr/bin/env bash
set -Eeuo pipefail

readonly CLUSTER_NAME="kaviont-local"
readonly KUBE_CONTEXT="kind-${CLUSTER_NAME}"
readonly IMAGE="kaviont/hello-api:local"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but was not found on PATH." >&2
  exit 1
fi

docker info >/dev/null

echo "Building the local runtime image with BuildKit dependency caching."
docker build --target runtime --tag "${IMAGE}" "${REPO_ROOT}/workloads/hello-api"

if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -Fxq "${CLUSTER_NAME}"; then
  echo "Loading ${IMAGE} into kind cluster ${CLUSTER_NAME}."
  kind load docker-image "${IMAGE}" --name "${CLUSTER_NAME}"

  if command -v kubectl >/dev/null 2>&1 && kubectl --context "${KUBE_CONTEXT}" -n kaviont-local get deployment hello-api-local >/dev/null 2>&1; then
    echo "Restarting the local workload to use the newly loaded image."
    kubectl --context "${KUBE_CONTEXT}" -n kaviont-local rollout restart deployment/hello-api-local
  fi
else
  echo "Image built. Run 'make local-up' to create kind and load it."
fi
