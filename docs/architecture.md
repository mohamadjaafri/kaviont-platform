# Architecture

## Goals

Kaviont provides a repeatable, minimal cloud platform foundation for a small sample workload. The goal is to demonstrate infrastructure design and operational controls rather than to represent a production deployment for a real organization.

## Logical components

- Terraform state foundation: a dedicated Azure Storage account provisioned by an isolated bootstrap root.
- State backend: Azure Blob Storage with Entra ID data-plane authorization, blob versioning, soft delete, and native lease-based locking.
- Resource group: lifecycle boundary for the development environment.
- Virtual network: 10.40.0.0/16 address space.
- AKS subnet: 10.40.0.0/20, used by the node pool.
- Private-endpoint subnet: 10.40.32.0/24, reserved for a later private networking iteration.
- Azure Container Registry: Basic tier, registry admin user disabled.
- AKS: Azure CNI Overlay, Cilium network policy/data plane, Azure RBAC, local accounts disabled, OIDC issuer and Workload Identity enabled.
- Control-plane identity: user-assigned managed identity with Network Contributor scoped to the AKS subnet.
- Kubelet: AKS-managed identity with AcrPull scoped to the project registry.
- Azure Key Vault: RBAC authorization, soft delete, purge protection, and a dedicated vault for the sample workload.
- hello-api identity: dedicated user-assigned managed identity, federated only to system:serviceaccount:demo:hello-api.
- Argo CD: upstream v3.6.1 non-HA installation in namespace argocd.
- AppProject: allows only the Kaviont Git repository, in-cluster destination, demo namespace, and resource kinds used by hello-api.
- Application: tracks main and renders the charts/hello-api chart using values-gitops.yaml.

## Terraform state lifecycle

The bootstrap/state root creates the state resource group, storage account, and Storage Blob Data Contributor assignment for the identity running the bootstrap. It initially uses local state because the remote storage does not exist yet.

The operator creates a private tfstate container using Azure CLI with Entra ID authentication. The bootstrap root's local state is then migrated to bootstrap.terraform.tfstate in that container. The development root uses a separate blob key, dev.terraform.tfstate.

Both roots declare the azurerm backend with use_azuread_auth = true. Local commands set ARM_USE_CLI=true after an interactive az login. Automation can use ARM_USE_OIDC=true and a federated identity instead; this repository does not yet configure an automated apply workflow.

Azure Blob Storage provides state locking and consistency checking. Blob versioning and soft delete provide recovery options for accidental state changes or deletion.

## Workload identity flow

1. AKS publishes an OIDC issuer and enables the Workload Identity webhook.
2. Terraform creates a user-assigned managed identity for hello-api.
3. A federated identity credential trusts the AKS issuer, audience api://AzureADTokenExchange, and exact subject system:serviceaccount:demo:hello-api.
4. The Helm chart annotates the Kubernetes service account with the identity client ID and labels the pod template with azure.workload.identity/use: true.
5. The webhook projects a service-account token into the pod.
6. Azure Identity's DefaultAzureCredential exchanges that token for a Microsoft Entra token.
7. The identity uses its Key Vault Secrets User role to read the demo secret.
8. The API returns only a Boolean status. It never exposes the secret value.

## GitOps reconciliation

Terraform owns Azure infrastructure: resource groups, network, AKS, ACR, Key Vault, managed identities, role assignments, and the remote state account.

Argo CD owns only the hello-api workload resources in Kubernetes namespace demo. It watches this repository's main branch and renders charts/hello-api with the generated values-gitops.yaml file.

The Application uses an AppProject that allows one Git source, one in-cluster destination, and the namespaced resource kinds required by the chart. Cluster-scoped resources are not allowed. The Application has automated sync, prune, and self-heal enabled with a bounded retry policy.

The environment values file is rendered from Terraform outputs by scripts/configure-gitops.py. It includes the ACR login server, managed identity client ID, Key Vault URI, image tag, and demo secret name. Those values identify infrastructure and are not secret material. Key Vault secret values remain in Key Vault.

The bootstrap script installs the pinned upstream Argo CD release and applies the AppProject and Application manifests using Kustomize. The controller then reconciles the demo namespace. Workload changes are made through reviewed Git commits; do not use a second Helm release to manage the same resources.

## Network allocation

| Purpose | CIDR |
|---|---|
| VNet | 10.40.0.0/16 |
| AKS node subnet | 10.40.0.0/20 |
| Private endpoint subnet (reserved) | 10.40.32.0/24 |
| Kubernetes pods (overlay) | 10.41.0.0/16 |
| Kubernetes services | 10.42.0.0/16 |
| CoreDNS service IP | 10.42.0.10 |

All ranges are examples. Before deployment, verify they do not overlap with networks connected to your Azure environment.

## Trust boundaries

- Terraform bootstrap operator: creates the state storage account and grants the state data-plane role to the current Entra principal.
- Terraform state: dedicated storage account, private blob container, Entra ID data-plane authentication, no Shared Key access. Public network access remains enabled in this development profile.
- Terraform execution identity: operator or CI identity with deployment permissions in the target subscription/resource group.
- Argo CD controller: reconciles one Git source into namespace demo with a narrow namespace-resource allowlist. It does not manage Azure infrastructure or Terraform state.
- AKS control plane: user-assigned managed identity, scoped to the node subnet.
- Kubelet: AKS-managed identity, scoped to read from ACR.
- hello-api: dedicated user-assigned identity with federated trust to one service account and read-only Key Vault role.
- Key Vault: RBAC authorization, public endpoint in this development profile. Private endpoint and private DNS are roadmap items.
- Public AKS API: restricted by an explicit CIDR allowlist supplied at deployment time.

## Availability and operations

The first environment uses a small system node pool with autoscaling bounds. It is a learning and validation environment, not an HA production topology. Argo CD is also installed in a non-HA profile to keep the example small. A production implementation would define separate system and user pools, zones supported by the chosen VM SKU, private control-plane access, Argo CD HA and SSO, maintenance windows, backup/restore objectives, and capacity testing.

## Cost controls

The state account uses Standard LRS and is expected to be low-cost, but pricing varies by region, storage, transactions, redundancy, and retention. AKS worker nodes, managed disks, load balancers, ACR storage, Key Vault operations, Argo CD, and network egress can incur additional charges. Keep the development environment small, review the Azure cost estimate before applying, and destroy development resources when unused.

The state storage account is deliberately separate from the development resource group. Do not delete it as part of the normal development teardown. Key Vault soft delete and purge protection mean a destroyed vault can remain recoverable and its name may not be reusable immediately.
