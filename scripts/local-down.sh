#!/usr/bin/env bash
set -Eeuo pipefail

readonly CLUSTER_NAME="kaviont-local"

if ! command -v kind >/dev/null 2>&1; then
  echo "kind is required but was not found on PATH." >&2
  exit 1
fi

if kind get clusters | grep -Fxq "${CLUSTER_NAME}"; then
  echo "Deleting only the Kaviont local kind cluster and its ephemeral test secret."
  kind delete cluster --name "${CLUSTER_NAME}"
else
  echo "Kaviont local cluster does not exist."
fi
