# ADR 0003: Azure Blob backend for Terraform state

- Status: Accepted
- Date: 2026-11-12

## Context

The development and bootstrap roots initially use local state during their first initialization. Local state is unsuitable for repeatable team workflows because it is tied to an operator's machine and does not provide a shared locking boundary.

Terraform state can contain sensitive values returned by providers. The backend must provide centralized access control, state locking, and a recovery path without introducing long-lived storage keys into configuration or CI.

## Decision

Use a dedicated Azure StorageV2 account in a separate kaviont-state-rg resource group.

The account uses Standard LRS, HTTPS-only traffic, TLS 1.2, infrastructure encryption, blob versioning, and a 14-day blob soft-delete retention window. Public nested blob access is disabled. Shared Key authorization is disabled and Entra ID OAuth is the default.

Use a private tfstate container and the Terraform azurerm backend with use_azuread_auth = true. Local operator workflows authenticate through Azure CLI. Azure Blob Storage provides native blob lease locking and consistency checking.

Keep separate state blobs:
- bootstrap.terraform.tfstate
- dev.terraform.tfstate

The bootstrap root starts with local state because it must create the remote state account. The runbook migrates this initial state after the storage account and private container exist.

The bootstrap operator receives Storage Blob Data Contributor at the dedicated state-account scope. This scope is limited to the single-purpose Kaviont state account and allows the operator to create the container and migrate both roots. Future automation identities should receive the same role at the tfstate container scope only.

The storage account uses prevent_destroy = true so a normal Terraform destroy plan cannot remove the backend.

## Consequences

- Terraform operations from authorized machines use shared remote state and native locking.
- State access relies on Entra ID RBAC rather than storage account keys, SAS tokens, or client secrets.
- The bootstrap procedure has a short-lived local-state phase that the operator must protect and migrate.
- The account's public endpoint is still enabled in the development profile. Private endpoint and private DNS are future work.
- The current CI workflow validates Terraform without authenticating to Azure. A later OIDC deployment workflow must use a dedicated federated identity, container-scoped state access, protected environments, and reviewed deployment permissions.
- The state account is independent of the development resource group and must not be removed by routine environment cleanup.
