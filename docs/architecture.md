# Architecture

## Goals

Kaviont provides a repeatable, minimal cloud platform foundation for a small sample workload. The goal is to demonstrate infrastructure design and operational controls rather than to represent a production deployment for a real organization.

## Logical components

- Resource group: lifecycle boundary for the development environment.
- Virtual network: 10.40.0.0/16 address space.
- AKS subnet: 10.40.0.0/20, used by the node pool.
- Private-endpoint subnet: 10.40.32.0/24, reserved for a later private networking iteration.
- Azure Container Registry: Basic tier, registry admin user disabled.
- AKS: Azure CNI Overlay, Cilium network policy/data plane, Azure RBAC, local accounts disabled, OIDC issuer and Workload Identity enabled.
- Control-plane identity: user-assigned managed identity with Network Contributor scoped to the AKS subnet.
- Kubelet identity: managed by AKS, with AcrPull scoped to the project registry.
- Azure Key Vault: RBAC authorization, soft delete, purge protection, and a dedicated vault for the sample workload.
- hello-api identity: dedicated user-assigned managed identity, federated only to system:serviceaccount:demo:hello-api.

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

## Workload identity flow

1. AKS publishes an OIDC issuer and enables the Workload Identity webhook.
2. Terraform creates a user-assigned managed identity for hello-api.
3. A federated identity credential trusts the AKS issuer, audience api://AzureADTokenExchange, and exact subject system:serviceaccount:demo:hello-api.
4. The Helm chart annotates the Kubernetes service account with the identity client ID and labels the pod template with azure.workload.identity/use: true.
5. The webhook projects a service-account token into the pod.
6. Azure Identity's DefaultAzureCredential exchanges that token for a Microsoft Entra token.
7. The identity uses its Key Vault Secrets User role to read the demo secret.
8. The API returns only a Boolean status. It never exposes the secret value.

## Trust boundaries

- Terraform execution identity: operator or CI identity with deployment permissions in the target subscription/resource group.
- AKS control plane: user-assigned managed identity, scoped to the node subnet.
- Kubelet: AKS-managed identity, scoped to read from ACR.
- hello-api: dedicated user-assigned identity with federated trust to one service account and read-only Key Vault role.
- Key Vault: RBAC authorization, public endpoint in this development profile. Private endpoint and private DNS are roadmap items.
- Public AKS API: restricted by an explicit CIDR allowlist supplied at deployment time.

## Availability and operations

The first environment uses a small system node pool with autoscaling bounds. It is a learning and validation environment, not an HA production topology. A production implementation would define separate system and user pools, zones supported by the chosen VM SKU, private control-plane access, maintenance windows, backup/restore objectives, and capacity testing.

## Cost controls

AKS worker nodes, managed disks, load balancers, ACR storage, Key Vault operations, and network egress can incur charges. Keep the development environment small, review the Azure cost estimate before applying, and destroy the environment when it is not in use. Key Vault soft delete and purge protection mean a destroyed vault can remain recoverable and its name may not be immediately reusable. The Terraform configuration intentionally does not claim a fixed monthly cost because pricing depends on region, SKU, uptime, storage, and traffic.
