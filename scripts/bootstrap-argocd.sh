#!/usr/bin/env bash
set -Eeuo pipefail

readonly ARGOCD_VERSION="v3.6.1"
readonly ARGOCD_MANIFEST_URL="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly GITOPS_VALUES="${REPO_ROOT}/charts/hello-api/values-gitops.yaml"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required but was not found on PATH." >&2
  exit 1
fi

if ! kubectl config current-context >/dev/null 2>&1; then
  echo "No Kubernetes context is configured. Connect kubectl to the target AKS cluster first." >&2
  exit 1
fi

if ! kubectl get nodes >/dev/null 2>&1; then
  echo "The current Kubernetes context is not reachable or lacks cluster read access." >&2
  exit 1
fi

if [[ ! -s "${GITOPS_VALUES}" ]]; then
  echo "Missing charts/hello-api/values-gitops.yaml." >&2
  echo "Run python scripts/configure-gitops.py, commit the generated file, and push it to main first." >&2
  exit 1
fi

if grep -q 'REPLACE_WITH_' "${GITOPS_VALUES}"; then
  echo "GitOps values still contain placeholders. Configure and commit them before bootstrapping Argo CD." >&2
  exit 1
fi

echo "Installing Argo CD ${ARGOCD_VERSION} into namespace argocd."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply --server-side --force-conflicts -n argocd -f "${ARGOCD_MANIFEST_URL}"

kubectl wait --for=condition=Established --timeout=180s \
  crd/applications.argoproj.io crd/appprojects.argoproj.io
kubectl rollout status deployment/argocd-server -n argocd --timeout=300s

# The demo namespace is pre-created by the bootstrap operator. Keeping it outside
# the Application lets the AppProject deny every cluster-scoped resource kind.
kubectl create namespace demo --dry-run=client -o yaml | kubectl apply -f -

echo "Registering the restricted Kaviont AppProject and hello-api Application."
kubectl apply -k "${REPO_ROOT}/gitops/argocd"

echo
echo "Argo CD bootstrap completed."
echo "Check the application with: kubectl get applications -n argocd"
echo "Forward the UI with: kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "Open https://localhost:8080 and retrieve the initial password using the runbook."
