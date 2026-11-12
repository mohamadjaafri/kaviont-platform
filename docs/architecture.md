# Architecture

## Goals

Kaviont provides a repeatable, minimal cloud platform foundation for a small sample workload. The goal is to demonstrate infrastructure design and operational controls rather than to represent a production deployment for a real organization.

## Logical components

- **Resource group:** lifecycle boundary for the development environment.
- **Virtual network:** `10.40.0.0/16` address space.
- **AKS subnet:** `10.40.0.0/20`, used by the node pool.
- **Private-endpoint subnet:** `10.40.32.0/24`, reserved for a later private networking iteration.
- **Azure Container Registry:** Basic tier, registry admin user disabled.
- **AKS:** Azure CNI Overlay, Cilium network policy/data plane, Azure RBAC, local accounts disabled, OIDC issuer and Workload Identity enabled.
- **Control-plane identity:** user-assigned managed identity with Network Contributor scoped to the AKS subnet.
- **Kubelet identity:** managed by AKS, with AcrPull scoped to the project registry.

## Network allocation

| Purpose | CIDR |
|---|---|
| VNet | `10.40.0.0/16` |
| AKS node subnet | `10.40.0.0/20` |
| Private endpoint subnet (reserved) | `10.40.32.0/24` |
| Kubernetes pods (overlay) | `10.41.0.0/16` |
| Kubernetes services | `10.42.0.0/16` |
| CoreDNS service IP | `10.42.0.10` |

All ranges are examples. Before deployment, verify they do not overlap with networks connected to your Azure environment.

## Identity flow

1. Terraform creates a user-assigned identity for the AKS control plane.
2. The identity receives Network Contributor on the AKS subnet only.
3. AKS uses the user-assigned identity for control-plane operations.
4. AKS provisions a kubelet identity.
5. The kubelet identity receives AcrPull only on the project ACR.
6. Application-to-Azure authentication can be added using AKS OIDC federation and Microsoft Entra Workload Identity. No client secret is needed in the application manifest.

## Trust boundaries

- Terraform execution identity: operator or CI identity with deployment permissions in the target subscription/resource group.
- AKS control plane: user-assigned managed identity, scoped to the node subnet.
- Kubelet: AKS-managed identity, scoped to read from ACR.
- Workload: Kubernetes service account plus Entra federation (to be configured in a later increment).
- Public AKS API: restricted by an explicit CIDR allowlist supplied at deployment time.

## Availability and operations

The first environment uses a small system node pool with autoscaling bounds. It is a learning and validation environment, not an HA production topology. A production implementation would define separate system and user pools, zones supported by the chosen VM SKU, private control-plane access, maintenance windows, backup/restore objectives, and capacity testing.

## Cost controls

AKS worker nodes, managed disks, load balancers, ACR storage, and network egress can incur charges. Keep the development environment small, review the Azure cost estimate before applying, and destroy the environment when it is not in use. The Terraform configuration intentionally does not claim a fixed monthly cost because pricing depends on region, SKU, uptime, storage, and traffic.
