# Security and cost notes

## Security controls

- No service-principal client secret is embedded in Terraform or Kubernetes manifests.
- AKS control plane uses a user-assigned managed identity.
- Network Contributor is scoped to the AKS node subnet.
- Kubelet receives AcrPull scoped to the project registry.
- ACR admin user is disabled.
- AKS local accounts are disabled and Azure RBAC integration is enabled.
- AKS API endpoint access requires an explicit CIDR allowlist.
- OIDC issuer and Workload Identity are enabled.
- hello-api uses a dedicated user-assigned identity with a federated credential restricted to one AKS issuer, audience, namespace, and service account.
- The workload identity receives only the Key Vault Secrets User role on the dedicated project vault.
- Key Vault uses Azure RBAC, soft delete, and purge protection.
- The sample container runs as a non-root user with a read-only root filesystem.
- Helm defines CPU/memory requests and limits, health probes, and a namespace-scoped ingress policy.
- The secret-status API reports presence only. It never returns or logs secret values.

## Important boundaries

The development Key Vault uses its public endpoint. Access still requires Microsoft Entra authentication and an assigned data-plane role, but private endpoint, private DNS, and network isolation are not included yet.

The first increment does not provide a private AKS API endpoint, private ACR endpoint, remote state, policy-as-code enforcement, image signing, centralized secret rotation, or production HA. Those are roadmap items, not claims of current capability.

The hello-api identity receives read access at the vault scope. This is suitable for a dedicated demo vault containing only workload-owned sample secrets. For shared vaults, prefer secret-scoped assignments where operationally appropriate.

Do not grant the Terraform execution identity Owner at subscription scope solely to make the example work. Use the narrowest role set that meets the deployment requirements and review role assignments before applying.

Terraform state may contain sensitive infrastructure metadata. Use a secured remote backend with access control and locking before collaborating or using the project beyond a local sandbox.

Key Vault purge protection cannot be disabled after activation. A destroyed vault can remain recoverable, and its name may not be reusable immediately.

## Cost

AKS nodes and attached disks run continuously until the environment is destroyed. ACR storage, load balancers, egress, Key Vault operations, and monitoring add further cost. Use a small development profile and destroy unused environments. Check current Azure pricing for your region and VM SKU before provisioning.
