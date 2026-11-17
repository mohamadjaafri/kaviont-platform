#!/usr/bin/env bash
set -Eeuo pipefail

readonly CLUSTER_NAME="kaviont-local"
readonly KUBE_CONTEXT="kind-${CLUSTER_NAME}"
readonly ARGOCD_VERSION="v3.6.1"
readonly ARGOCD_MANIFEST_URL="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

for command in docker kind kubectl openssl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "${command} is required but was not found on PATH." >&2
    exit 1
  fi
done

docker info >/dev/null

if ! kind get clusters | grep -Fxq "${CLUSTER_NAME}"; then
  echo "Creating the single-node local Kubernetes cluster."
  kind create cluster --name "${CLUSTER_NAME}" --config "${REPO_ROOT}/kind/kaviont-local.yaml" --wait 120s
else
  echo "Reusing existing kind cluster ${CLUSTER_NAME}."
fi

kubectl config use-context "${KUBE_CONTEXT}" >/dev/null
kubectl --context "${KUBE_CONTEXT}" get nodes

bash "${SCRIPT_DIR}/local-build.sh"

echo "Preparing local namespaces and an ephemeral, non-production demo secret."
kubectl --context "${KUBE_CONTEXT}" create namespace argocd --dry-run=client -o yaml | kubectl --context "${KUBE_CONTEXT}" apply -f -
kubectl --context "${KUBE_CONTEXT}" create namespace kaviont-local --dry-run=client -o yaml | kubectl --context "${KUBE_CONTEXT}" apply -f -
kubectl --context "${KUBE_CONTEXT}" -n kaviont-local create secret generic hello-api-local \
  --from-literal=demo-secret="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl --context "${KUBE_CONTEXT}" apply -f -

echo "Installing Argo CD ${ARGOCD_VERSION}."
kubectl --context "${KUBE_CONTEXT}" apply --server-side --force-conflicts -n argocd -f "${ARGOCD_MANIFEST_URL}"
kubectl --context "${KUBE_CONTEXT}" wait --for=condition=Established --timeout=180s \
  crd/applications.argoproj.io crd/appprojects.argoproj.io
kubectl --context "${KUBE_CONTEXT}" rollout status deployment/argocd-server -n argocd --timeout=300s

echo "Registering the isolated local AppProject and Application."
kubectl --context "${KUBE_CONTEXT}" apply -k "${REPO_ROOT}/gitops/argocd/local"

wait_for_argo_application() {
  local application_name="$1"
  local timeout_seconds="${2:-600}"
  local started_at="${SECONDS}"
  local app_state=""

  echo "Waiting for Argo CD application ${application_name} to become Synced and Healthy."
  while (( SECONDS - started_at < timeout_seconds )); do
    app_state="$(
      kubectl --context "${KUBE_CONTEXT}" -n argocd get application "${application_name}" \
        -o jsonpath='{.status.sync.status}|{.status.health.status}' 2>/dev/null || true
    )"

    if [[ "${app_state}" == "Synced|Healthy" ]]; then
      echo "Argo CD application ${application_name}: Synced and Healthy."
      return 0
    fi

    if (( (SECONDS - started_at) > 0 && (SECONDS - started_at) % 30 < 5 )); then
      echo "Still waiting for ${application_name} (sync/health: ${app_state:-Pending})."
    fi
    sleep 5
  done

  echo "Timed out waiting for Argo CD application ${application_name} (sync/health: ${app_state:-Pending})." >&2
  kubectl --context "${KUBE_CONTEXT}" -n argocd describe application "${application_name}" >&2 || true
  kubectl --context "${KUBE_CONTEXT}" -n kaviont-local get pods,svc >&2 || true
  return 1
}

echo "Waiting for Argo CD to reconcile the local workload from the main branch."
wait_for_argo_application "hello-api-local" 600
kubectl --context "${KUBE_CONTEXT}" rollout status deployment/hello-api-local -n kaviont-local --timeout=300s

echo "Waiting for Argo CD to deploy the local OpenTelemetry Collector."
wait_for_argo_application "otel-collector-local" 600
kubectl --context "${KUBE_CONTEXT}" rollout status deployment/otel-collector -n kaviont-local --timeout=300s

echo
echo "Kaviont local Kubernetes environment is ready."
echo "Argo CD: kubectl --context ${KUBE_CONTEXT} get applications -n argocd"
echo "Workload: kubectl --context ${KUBE_CONTEXT} get pods,svc -n kaviont-local"
echo "API: make local-forward  (http://127.0.0.1:8081)"
echo "Argo CD UI: kubectl --context ${KUBE_CONTEXT} port-forward svc/argocd-server -n argocd 8080:443"
