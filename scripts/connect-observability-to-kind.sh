#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly KUBE_CONTEXT="kind-kaviont-local"
readonly KUBE_NAMESPACE="kaviont-local"

cd "${REPO_ROOT}"

if ! docker network inspect kind >/dev/null 2>&1; then
  echo "The kind Docker network is not present. Keeping the standalone Compose observability stack unchanged."
  exit 0
fi

for service in prometheus blackbox-exporter tempo; do
  container_id="$(docker compose --profile observability ps -q "${service}")"
  if [[ -z "${container_id}" ]]; then
    echo "Compose service ${service} is not running. Start it with 'make observability-up'." >&2
    exit 1
  fi

  networks="$(docker inspect --format '{{json .NetworkSettings.Networks}}' "${container_id}")"
  if grep -Eq '"kind"[[:space:]]*:' <<< "${networks}"; then
    echo "${service} is already connected to the kind Docker network."
  else
    docker network connect kind "${container_id}"
    echo "Connected ${service} to the kind Docker network."
  fi
done

tempo_container_id="$(docker compose --profile observability ps -q tempo)"
tempo_ip="$(docker inspect --format '{{with index .NetworkSettings.Networks "kind"}}{{.IPAddress}}{{end}}' "${tempo_container_id}")"
if [[ -z "${tempo_ip}" ]]; then
  echo "Could not determine Tempo's IPv4 address on the kind Docker network." >&2
  exit 1
fi

# A standalone Compose stack may be used without the local kind cluster.
if ! kubectl --context "${KUBE_CONTEXT}" get namespace "${KUBE_NAMESPACE}" >/dev/null 2>&1; then
  echo "Tempo is attached to kind at ${tempo_ip}; no local Kubernetes namespace is present."
  exit 0
fi

if ! kubectl --context "${KUBE_CONTEXT}" -n "${KUBE_NAMESPACE}" get deployment otel-collector >/dev/null 2>&1; then
  echo "Tempo is attached to kind at ${tempo_ip}; the Kubernetes OTel Collector is not deployed yet."
  exit 0
fi

desired_endpoint="${tempo_ip}:4317"
current_endpoint="$(
  kubectl --context "${KUBE_CONTEXT}" -n "${KUBE_NAMESPACE}" get configmap otel-collector-runtime \
    -o 'jsonpath={.data.tempo_otlp_endpoint}' 2>/dev/null || true
)"

kubectl --context "${KUBE_CONTEXT}" -n "${KUBE_NAMESPACE}" create configmap otel-collector-runtime \
  --from-literal="tempo_otlp_endpoint=${desired_endpoint}" \
  --dry-run=client -o yaml | kubectl --context "${KUBE_CONTEXT}" apply -f -

if [[ "${current_endpoint}" != "${desired_endpoint}" ]]; then
  echo "Updated Kubernetes Collector Tempo endpoint to ${desired_endpoint}."
  kubectl --context "${KUBE_CONTEXT}" -n "${KUBE_NAMESPACE}" rollout restart deployment/otel-collector
else
  echo "Kubernetes Collector already targets Tempo at ${desired_endpoint}."
fi

kubectl --context "${KUBE_CONTEXT}" -n "${KUBE_NAMESPACE}" rollout status deployment/otel-collector --timeout=180s
echo "Kubernetes trace export is configured for the central Tempo backend."
