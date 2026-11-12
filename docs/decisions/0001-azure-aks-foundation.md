# ADR 0001: Azure AKS as the first platform target

- Status: Accepted for the first reference implementation
- Date: 2026-11-12

## Context

The project needs a concrete platform target to demonstrate repeatable infrastructure, Kubernetes operations, workload delivery, and cloud identity patterns. It must remain an independent portfolio project and avoid any employer- or customer-specific design.

## Decision

Use Microsoft Azure as the first provider and AKS as the managed Kubernetes service. Provision the foundation with Terraform modules. Use Azure CNI Overlay with Cilium, a user-assigned control-plane identity, Azure RBAC, disabled local cluster accounts, OIDC issuer, and Workload Identity support.

## Consequences

- The project demonstrates a real managed Kubernetes platform rather than only local manifests.
- Azure-specific details live behind Terraform modules and environment inputs.
- The first iteration is Azure-focused; AWS and GCP implementations are out of scope.
- The development API endpoint is public but restricted by an explicit CIDR allowlist. A private AKS endpoint is a planned follow-up.
- Remote Terraform state and a CI deployment identity are not included in this first iteration.
- AKS and related resources incur costs while provisioned.

## Alternatives considered

- **Local-only Kubernetes (kind/k3d):** cheaper and useful for fast tests, but it does not demonstrate cloud identity or network integration.
- **Multi-cloud from day one:** increases scope and duplicates design before the first baseline is validated.
- **Private AKS API in the first iteration:** stronger isolation but requires private DNS and operator connectivity design; reserved for the next networking increment.
