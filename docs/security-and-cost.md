# Security and cost notes

## Security controls in the first iteration

- No service-principal client secret is embedded in Terraform.
- AKS control plane uses a user-assigned managed identity.
- Network Contributor is scoped to the AKS node subnet.
- Kubelet receives AcrPull scoped to the project registry.
- ACR admin user is disabled.
- AKS local accounts are disabled and Azure RBAC integration is enabled.
- AKS API endpoint access requires an explicit CIDR allowlist.
- OIDC issuer and Workload Identity are enabled for future workload federation.
- The sample container runs as a non-root user with a read-only root filesystem.
- Helm defines CPU/memory requests and limits, health probes, and a namespace-scoped ingress policy.

## Important boundaries

The first iteration does not provide a private API endpoint, private ACR endpoint, remote state, policy-as-code enforcement, image signing, or centralized secret delivery. Those are roadmap items, not claims of current capability.

Do not grant the Terraform execution identity Owner at subscription scope solely to make the example work. Use the narrowest role set that meets the deployment requirements and review role assignments before applying.

Terraform state may contain sensitive infrastructure metadata. Use a secured remote backend with access control and locking before collaborating or using the project beyond a local sandbox.

## Cost

AKS nodes and attached disks run continuously until the environment is destroyed. ACR storage, load balancers, egress, and monitoring add further cost. Use a small development profile and destroy unused environments. Check current Azure pricing for your region and VM SKU before provisioning.
