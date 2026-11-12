# Runbook: provision and migrate Terraform remote state

## Design

Kaviont uses a dedicated Azure Storage account for Terraform state. The state account is separate from the development resource group and must outlive the AKS environment.

The backend uses Microsoft Entra ID data-plane authorization. Shared Key access is disabled. The private blob container stores separate state objects for the bootstrap and development roots. Azure Blob Storage provides native state locking. Blob versioning and a 14-day soft-delete retention window support recovery.

The state account public endpoint is enabled in this development profile. Requests still require Entra ID authentication and the appropriate data-plane role. Private endpoint and private DNS are not implemented yet.

## Prerequisites

- Azure CLI and Terraform 1.11.x.
- An authenticated Entra identity selected in the target subscription.
- Permission to create a resource group and storage account.
- Permission to create role assignments at the new storage account scope. This usually requires an appropriately scoped role such as Owner or User Access Administrator, not merely Contributor.
- A unique 4-8 character lowercase alphanumeric suffix. Reuse the same suffix in the dev environment.

## 1. Create the state storage account

From the repository root:

```bash
az login
az account set --subscription "<subscription-id>"
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv)"

cd infrastructure/terraform/bootstrap/state
cp terraform.tfvars.example terraform.tfvars
# Edit unique_suffix and subscription_id if needed.

terraform init -backend=false -input=false
terraform fmt -check
terraform validate
terraform plan -out=tfstate-bootstrap.tfplan
terraform apply tfstate-bootstrap.tfplan
```

The bootstrap root initially uses local state because the remote account does not exist yet. Keep this local state and plan file private. Do not commit either file.

The state storage account has prevent_destroy = true. It is intentionally protected from ordinary Terraform destroy operations.

## 2. Create the private state container

The bootstrap root assigns the currently authenticated Entra principal the Storage Blob Data Contributor role on the dedicated state account. This account is reserved for Kaviont Terraform state only.

Read the generated account name and create the container using Entra authentication:

```bash
STATE_STORAGE_ACCOUNT="$(terraform output -raw storage_account_name)"

# Role assignments can take time to propagate. Retry this command after propagation
# if Azure initially returns an authorization error.
az storage container create   --name tfstate   --account-name "$STATE_STORAGE_ACCOUNT"   --auth-mode login   --only-show-errors
```

The container is private by default. Do not pass a public access level.

## 3. Migrate the bootstrap state

Copy backend.hcl.example to backend.hcl in the bootstrap directory. Confirm storage_account_name matches the output from Terraform.

Authenticate the backend through the existing Azure CLI session:

```bash
export ARM_USE_CLI=true
terraform init -migrate-state -backend-config=backend.hcl
terraform plan
```

Review the migration prompt and confirm that Terraform should copy the existing local state to bootstrap.terraform.tfstate in the container. Verify that terraform state list returns the bootstrap resources after migration.

The local state file may remain on disk after migration. Keep it protected until the remote state is verified, then securely remove the local copy in accordance with your workstation policy.

## 4. Initialize the development root

Change to infrastructure/terraform/environments/dev. Copy backend.hcl.example to backend.hcl and confirm that the storage account name and container match the bootstrap outputs. The example uses a different blob key so the two Terraform roots do not share state.

If the development root already has local state, migrate it:

```bash
export ARM_USE_CLI=true
terraform init -migrate-state -backend-config=backend.hcl
terraform plan
```

If the development root has never been applied and has no local state, initialize it without the migration flag:

```bash
export ARM_USE_CLI=true
terraform init -backend-config=backend.hcl
terraform validate
terraform plan
```

Review the plan before applying. The state key is dev.terraform.tfstate.

## 5. Verify state access and locking

Run these commands from each Terraform root:

```bash
terraform state list
terraform plan
```

Use separate terminals to test concurrent state operations only in a disposable test environment. Azure Blob leases provide the backend's state lock. Do not interrupt a state write or manually delete a lease to bypass a lock.

## Automation permissions

The bootstrap operator currently receives Storage Blob Data Contributor at the dedicated storage-account scope so it can create the container and migrate both states.

A separate GitHub Actions identity should receive Storage Blob Data Contributor at the tfstate container scope only. Use GitHub OIDC federation rather than a client secret. The CI workflow currently validates source code only and does not authenticate to or modify Azure.

To use GitHub OIDC later, set ARM_USE_OIDC=true and configure the backend identity inputs and federated credential for the intended GitHub repository and branch/environment. Do not grant the CI identity access to the whole subscription just to read or lock Terraform state.

## Recovery and lifecycle

- Use Azure blob versions and soft delete to recover an accidentally changed or deleted state blob.
- Before state surgery, stop all Terraform runs and take a protected backup of the current state.
- Never edit the state JSON directly.
- Do not destroy the state resource group or account during a development environment teardown.
- To retire the backend, first migrate every state object to a separately governed backend or export and archive it under an approved procedure. Only then remove the prevent_destroy guard and destroy the state account deliberately.

## Troubleshooting

- AuthorizationPermissionMismatch: verify Storage Blob Data Contributor on the storage account for the bootstrap operator or on the container for automation.
- ContainerNotFound: confirm the tfstate container exists and uses private access.
- Azure CLI authentication failure: run az account show and verify the selected tenant and subscription.
- Terraform reports a backend configuration change: rerun terraform init with the correct backend.hcl; use -migrate-state only when migrating a local state.
- State lock error: identify the active Terraform operation and wait for it to complete. Do not force-unlock unless the original operation is confirmed dead and you have reviewed the lease and state.
