# ADR 0004: Argo CD as the Kubernetes GitOps reconciler

- Status: Accepted
- Date: 2026-11-13

## Context

Kaviont uses Terraform to provision Azure infrastructure and Helm to package the hello-api workload. A direct Helm install makes the cluster state dependent on an operator's workstation and leaves ongoing drift detection and reconciliation to manual processes.

The workload configuration should be declarative, reviewed in Git, and reconciled by a controller running in AKS. The controller must have a narrow source, destination, and resource scope.

## Decision

Install upstream Argo CD v3.6.1 using the version-pinned non-HA installation manifest.

Create a dedicated AppProject named kaviont-dev. It allows only the Kaviont public Git repository, the in-cluster Kubernetes API, the demo namespace, and the resource kinds rendered by the hello-api chart. It does not allow cluster-scoped resources.

Create a hello-api Application that tracks the main branch and renders the charts/hello-api Helm chart using values-gitops.yaml. Enable automated synchronization, pruning, self-healing, namespace creation, and bounded retry with backoff.

Keep infrastructure management in Terraform. Argo CD owns only the hello-api namespace resources. Do not use a parallel Helm release or imperative kubectl changes to manage the same resources.

Generate the environment-specific values file from Terraform outputs. The file contains ACR login server, managed identity client ID, and Key Vault URI. These are configuration identifiers, not secret values. Secret material remains in Key Vault and is consumed by the workload through federated Workload Identity.

## Consequences

- Workload configuration changes are reviewed through Git pull requests.
- Argo CD detects divergence and reconciles the demo application to the desired Git state.
- Automated pruning can delete resources removed from the Helm chart. The AppProject limits the application blast radius.
- The first installation still requires an AKS operator with cluster-admin-equivalent permissions to install Argo CD CRDs and controllers.
- The initial setup uses the upstream non-HA profile, built-in admin account, and port-forwarded UI. SSO, ingress TLS, high availability, and production hardening remain future work.
- Argo CD does not provision Azure infrastructure or manage Terraform state.
