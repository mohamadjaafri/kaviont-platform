# Runbook: configure hello-api Workload Identity and Key Vault

This runbook assumes the Terraform environment has been provisioned and kubectl is connected to the resulting AKS cluster.

## 1. Read the Terraform outputs

From the repository root, enter the dev environment and read these outputs into shell variables:

- RESOURCE_GROUP from terraform output -raw resource_group_name
- AKS_NAME from terraform output -raw aks_cluster_name
- ACR_NAME from terraform output -raw acr_name
- ACR_LOGIN_SERVER from terraform output -raw acr_login_server
- KEY_VAULT_NAME from terraform output -raw key_vault_name
- KEY_VAULT_URI from terraform output -raw key_vault_uri
- HELLO_API_CLIENT_ID from terraform output -raw hello_api_identity_client_id
- AZURE_TENANT_ID from terraform output -raw azure_tenant_id

Return to the repository root after reading the outputs.

## 2. Connect to AKS and create a demo secret

Run az aks get-credentials with the resource group and AKS name, then confirm that kubectl get nodes succeeds.

Create a demo secret using Azure CLI:

az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "platform-demo-token" --value "$(openssl rand -hex 32)" --query id --output tsv

The command prints only the secret resource ID, not the secret value. The Terraform execution identity needs permission to create secrets in this vault (for example, Key Vault Secrets Officer) or an administrator must create the demo secret.

## 3. Build and push the sample API

Build workloads/hello-api with Docker and tag it as $ACR_LOGIN_SERVER/hello-api:0.2.0. Authenticate with az acr login --name "$ACR_NAME", then push the image.

## 4. Deploy with federated workload identity

Install or upgrade the hello-api chart into namespace demo with these Helm values:

- workloadIdentity.enabled=true
- workloadIdentity.clientId=$HELLO_API_CLIENT_ID
- workloadIdentity.keyVaultUrl=$KEY_VAULT_URI
- workloadIdentity.secretName=platform-demo-token
- image.repository=$ACR_LOGIN_SERVER/hello-api
- image.tag=0.2.0

Wait for kubectl rollout status deployment/hello-api -n demo.

Inspect the service account and pod labels. The service account annotation must contain the managed identity client ID. The pod template must contain azure.workload.identity/use: true. The federated credential trusts only system:serviceaccount:demo:hello-api.

## 5. Verify without disclosing the secret

Port-forward service hello-api in namespace demo from local port 8080 to service port 80. Request http://127.0.0.1:8080/v1/secret-status.

Expected JSON response:

{"mode":"azure-key-vault","secret_configured":true}

The endpoint returns only whether the named secret is present and non-empty. It never returns the secret value.

## 6. Troubleshooting

- 401 or token exchange failure: verify AKS OIDC issuer, the FIC issuer, audience, and exact subject.
- 403 from Key Vault: verify the identity client ID on the service account and the Key Vault Secrets User role assignment. Allow time for role assignment propagation.
- Secret not found: verify the secret name and vault URI.
- No injected Azure environment variables: confirm the pod label azure.workload.identity/use: true and recreate the pod after changing service-account annotations.
- Network timeout: the development vault uses its public endpoint. Check DNS and outbound connectivity. Private endpoint routing is not included yet.

## 7. Clean up the application

Uninstall the hello-api Helm release and delete namespace demo before destroying the Terraform environment.

Destroying the Terraform environment deletes the Key Vault resource, but soft delete and purge protection can retain it for recovery. The vault name may not be available for immediate reuse. Do not disable purge protection merely to simplify the demo teardown.
