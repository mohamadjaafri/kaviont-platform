# Runbook: provision and deploy the development platform

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
4. In infrastructure/terraform/environments/dev, confirm backend.hcl points to the Kaviont state account and run ARM_USE_CLI=true terraform init -backend-config=backend.hcl.
5. Run terraform fmt -check, terraform validate, and terraform plan -out=tfplan.
6. Review the plan and run terraform apply tfplan.

The Terraform execution identity needs permission to create Azure resources and role assignments at the required scopes. Do not grant subscription-wide Owner merely to make the example work.

If the first apply fails immediately after a role assignment is created, inspect the Azure error and role propagation state before retrying. Do not apply repeatedly without understanding the failure.

## Connect and read outputs

From infrastructure/terraform/environments/dev, read these outputs into shell variables:

- RESOURCE_GROUP from resource_group_name
- AKS_NAME from aks_cluster_name
- ACR_NAME from acr_name
- ACR_LOGIN_SERVER from acr_login_server
- KEY_VAULT_NAME from key_vault_name
- KEY_VAULT_URI from key_vault_uri
- HELLO_API_CLIENT_ID from hello_api_identity_client_id
- AZURE_TENANT_ID from azure_tenant_id

Use az aks get-credentials with RESOURCE_GROUP and AKS_NAME, then confirm kubectl get nodes succeeds. Authenticate to ACR with az acr login --name "$ACR_NAME".

## Create the demo secret

The Terraform execution identity or an administrator must have the Key Vault Secrets Officer role on this dedicated development vault.

Create a non-production demo value with Azure CLI:

```bash
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "platform-demo-token" --value "$(openssl rand -hex 32)" --query id --output tsv
```

The command prints only the secret resource ID, not the secret value. Do not use a real credential.

## Build and push the sample API

From the repository root, build workloads/hello-api and tag it as $ACR_LOGIN_SERVER/hello-api:0.2.0. Push that image to the project ACR.

## Deploy with federated workload identity

Install or upgrade the hello-api chart into namespace demo with these values:

- workloadIdentity.enabled=true
- workloadIdentity.clientId=$HELLO_API_CLIENT_ID
- workloadIdentity.keyVaultUrl=$KEY_VAULT_URI
- workloadIdentity.secretName=platform-demo-token
- image.repository=$ACR_LOGIN_SERVER/hello-api
- image.tag=0.2.0

Wait for kubectl rollout status deployment/hello-api -n demo.

Inspect the service account and pod labels. The service account annotation must contain the managed identity client ID. The pod template must contain azure.workload.identity/use: true. The federated credential trusts only system:serviceaccount:demo:hello-api.

## Verify without disclosing the secret

Port-forward service hello-api in namespace demo from local port 8080 to service port 80. Request http://127.0.0.1:8080/v1/secret-status.

Expected JSON response:

```json
{"mode":"azure-key-vault","secret_configured":true}
```

The endpoint returns only whether the named secret is present and non-empty. It never returns the secret value.

## Troubleshooting

- 401 or token exchange failure: verify AKS OIDC issuer, FIC issuer, audience, and exact subject.
- 403 from Key Vault: verify the identity client ID on the service account and the Key Vault Secrets User role assignment. Allow time for role assignment propagation.
- Secret not found: verify the secret name and vault URI.
- No injected Azure environment variables: confirm the pod label azure.workload.identity/use: true and recreate the pod after changing service-account annotations.
- Network timeout: the development vault uses its public endpoint. Check DNS and outbound connectivity. Private endpoint routing is not included yet.

## Destroy the development environment

Uninstall the hello-api Helm release and remove namespace demo before destroying the development environment.

Run terraform plan -destroy -out=destroy.tfplan, review the plan, and then run terraform apply destroy.tfplan.

Do not destroy the bootstrap state resource group or storage account. It contains the state required to manage and recover this environment. A separate, deliberate state-retirement procedure is required before removing it.

Key Vault uses soft delete and purge protection. A destroyed vault can remain recoverable and its name may not be reusable immediately. Do not disable purge protection merely to simplify the demo teardown.
