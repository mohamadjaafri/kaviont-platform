# Security and cost notes

## Security controls

- Terraform state is stored in a dedicated Azure Storage account, separate from the development resource group.
- Storage account Shared Key authorization is disabled and default OAuth authentication is enabled.
- The state blob uses versioning and a 14-day soft-delete retention window.
- The state container is private and Azure Blob Storage provides native state locking.
- Terraform backend access uses Microsoft Entra ID data-plane authorization, not storage account keys or SAS tokens.
- The bootstrap operator receives Storage Blob Data Contributor on the dedicated state account. A separate automation principal should receive this role at the tfstate container scope only.
- Storage account transport is HTTPS-only with TLS 1.2 or later.
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

The state account and development Key Vault use public endpoints in this development profile. Authentication and data-plane access still require Microsoft Entra ID and the appropriate RBAC role. Private endpoints, private DNS, and network isolation are not included yet.

The GitHub Actions workflow currently validates source code only. It does not authenticate to Azure, read remote state, or deploy resources. A production pipeline should use GitHub OIDC federation, protected environments, approval gates, and a dedicated identity with container-scoped state access and narrowly scoped deployment permissions.

The development profile does not provide a private AKS API endpoint, private ACR endpoint, secret rotation, policy-as-code enforcement, image signing, centralized observability, or production HA. Those are roadmap items, not current capabilities.

The hello-api identity receives read access at the vault scope. This is suitable for a dedicated demo vault containing only workload-owned sample secrets. For shared vaults, prefer secret-scoped assignments where operationally appropriate.

Do not grant the Terraform execution identity Owner at subscription scope solely to make the example work. Use the narrowest role set that meets deployment and role-assignment requirements, and review role assignments before applying.

Terraform state can contain sensitive infrastructure metadata and values returned by providers. Treat state files, local backups, and plan files as sensitive. Never commit them or publish them as CI artifacts without a deliberate redaction strategy.

The state storage account has prevent_destroy enabled. This protects the account from ordinary Terraform destroy plans. Removing the guard requires a deliberate maintenance change and a verified state migration or backup plan.

Key Vault purge protection cannot be disabled after activation. A destroyed vault can remain recoverable, and its name may not be reusable immediately.

## Cost

The state account uses Standard LRS and stores a small number of state blobs. Storage transactions, versions, and retained deleted blobs can still incur charges. AKS nodes and attached disks run continuously until the development environment is destroyed. ACR storage, load balancers, egress, Key Vault operations, and monitoring add further cost. Use a small development profile and destroy unused resources. Check current Azure pricing for your region and VM SKU before provisioning.
