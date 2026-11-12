# ADR 0002: Federated workload identity and Key Vault

- Status: Accepted for the second reference implementation increment
- Date: 2026-11-12

## Context

The sample workload needs a cloud identity to read an application secret. Storing a client secret in Kubernetes manifests or GitHub repository variables would create a long-lived credential and expand the secret distribution surface.

## Decision

- Create a dedicated user-assigned managed identity for the hello-api workload.
- Trust only the AKS OIDC issuer and the exact Kubernetes subject system:serviceaccount:demo:hello-api through a federated identity credential.
- Use the api://AzureADTokenExchange audience.
- Enable Azure RBAC authorization on Key Vault.
- Grant the workload identity the Key Vault Secrets User role at the dedicated project vault scope.
- Keep Key Vault public network access enabled only for this development profile; identity and RBAC still gate data access. Private endpoint and private DNS are a separate follow-up.
- Use Azure Identity's DefaultAzureCredential and the Key Vault Secrets SDK in the sample API.
- Expose only a Boolean secret-presence result. Never return or log the secret value.

## Consequences

- No client secret or service-principal credential is required in the pod.
- The federated trust is constrained to one cluster issuer, namespace, and service account.
- The workload can read secrets from the dedicated vault. It cannot create, update, or delete them.
- The first iteration grants read access at vault scope, so use a dedicated vault for the sample workload. A later iteration can narrow permissions to an individual secret scope after secret creation.
- The AKS OIDC issuer and Workload Identity feature must be enabled.
- Role assignment and federation propagation can take several minutes.
- The development vault uses soft delete and purge protection. A destroyed vault can remain recoverable and its name may not be immediately reusable.

## Alternatives considered

- Kubernetes Secret containing a client secret: rejected because it stores and distributes a long-lived credential.
- AKS node identity for application access: rejected because all workloads using that node identity could inherit its permissions.
- Key Vault CSI Driver: deferred. The current API needs programmatic access and an SDK-backed example; a CSI-mounted secret is useful for file-based consumers but follows a different application pattern.
