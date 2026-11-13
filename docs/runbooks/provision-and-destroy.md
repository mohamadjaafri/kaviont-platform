# Runbook: provision the development platform

## Before provisioning

- Confirm the target Azure subscription and tenant.
- Complete docs/runbooks/terraform-remote-state.md and verify both Terraform roots use Azure Blob state.
- Confirm the operator identity can create the listed resources and role assignments.
- Check selected AKS VM SKU availability in the region.
- Select a globally unique ACR and Key Vault suffix.
- Set the API server allowlist to the operator's fixed public egress IP in CIDR notation.
- Review the expected cost for the selected region and VM size.

## Provision

From the repository root:

1. Sign in with Azure CLI and select the intended non-production subscription.
2. Copy infrastructure/terraform/environments/dev/terraform.tfvars.example to terraform.tfvars.
3. Edit unique_suffix and replace the documentation-only API-server CIDR with your fixed public egress IP.
4. In infrastructure/terraform/environments/dev, confirm backend.hcl points to the Kaviont state account and run `ARM_USE_CLI=true terraform init -backend-config=backend.hcl`.
5. Run `terraform fmt -check`, `terraform validate`, and `terraform plan -out=tfplan`.
6. Review the plan and run `terraform apply tfplan`.

The Terraform execution identity needs permission to create Azure resources and role assignments at the required scopes. Do not grant subscription-wide Owner merely to make the example work.

If the first apply fails immediately after a role assignment is created, inspect the Azure error and role propagation state before retrying. Do not apply repeatedly without understanding the failure.

## Connect to AKS

Read the resource group and AKS name from Terraform outputs and connect kubectl:

```bash
RESOURCE_GROUP="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw resource_group_name)"
AKS_NAME="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw aks_cluster_name)"
az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME"
kubectl get nodes
```

## Deploy the sample workload

Follow docs/runbooks/argocd-gitops.md. It creates the demo Key Vault secret, pushes the sample container to ACR, generates the GitOps values from Terraform outputs, installs Argo CD, and registers the hello-api Application.

Argo CD becomes the owner of the hello-api resources in namespace demo. Do not run a parallel Helm install or use kubectl to edit those resources.

## Destroy the development environment

First stop Argo CD from recreating the workload:

```bash
kubectl delete application hello-api -n argocd
kubectl delete namespace demo
```

Remove the Argo CD installation only when no other applications depend on it. Then follow docs/runbooks/terraform-remote-state.md for any state-related operations and use the Terraform destroy plan:

```bash
cd infrastructure/terraform/environments/dev
terraform plan -destroy -out=destroy.tfplan
terraform apply destroy.tfplan
```

Review the plan before confirming. Do not destroy the bootstrap state resource group or storage account. It contains the state required to manage and recover the development environment. A separate, deliberate state-retirement procedure is required before removing it.

Key Vault uses soft delete and purge protection. A destroyed vault can remain recoverable and its name may not be reusable immediately. Do not disable purge protection merely to simplify the demo teardown.
