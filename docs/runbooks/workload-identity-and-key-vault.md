# Runbook: configure hello-api Workload Identity and Key Vault

This runbook is the short entry point for enabling the sample API's Azure identity and secret integration. Deployment is managed by Argo CD, not a parallel Helm release. Complete docs/runbooks/argocd-gitops.md for the full GitOps workflow.

## 1. Read the Terraform outputs

From the repository root, read the values from the dev environment:

- ACR name: `terraform -chdir=infrastructure/terraform/environments/dev output -raw acr_name`
- ACR login server: `terraform -chdir=infrastructure/terraform/environments/dev output -raw acr_login_server`
- Key Vault name: `terraform -chdir=infrastructure/terraform/environments/dev output -raw key_vault_name`
- Key Vault URI: `terraform -chdir=infrastructure/terraform/environments/dev output -raw key_vault_uri`
- hello-api managed identity client ID: `terraform -chdir=infrastructure/terraform/environments/dev output -raw hello_api_identity_client_id`

## 2. Create a demo secret

The operator or an administrator must have Key Vault Secrets Officer on the dedicated development vault.

Create a random non-production value. Azure CLI returns only the secret resource ID:

```bash
KEY_VAULT_NAME="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw key_vault_name)"
az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "platform-demo-token" \
  --value "$(openssl rand -hex 32)" \
  --query id --output tsv
```

Do not use a real credential. The hello-api identity receives read-only Key Vault Secrets User permission and the API never returns the secret value.

## 3. Build and push the container image

Follow step 2 in docs/runbooks/argocd-gitops.md to build and push version 0.2.0 to the project ACR. The AKS kubelet identity already has AcrPull on that registry.

## 4. Configure the workload identity values

Run `python scripts/configure-gitops.py` from the repository root. The helper reads the ACR login server, managed identity client ID, and Key Vault URI from Terraform outputs and generates charts/hello-api/values-gitops.yaml.

Commit that generated, non-secret configuration to the main branch through a pull request. Do not place secret values, client secrets, passwords, or tokens in this file.

## 5. Deploy and verify

Follow docs/runbooks/argocd-gitops.md to install the pinned Argo CD release, register the restricted AppProject and Application, and verify the rollout.

The expected endpoint response is:

```json
{"mode":"azure-key-vault","secret_configured":true}
```

## Troubleshooting

- Token exchange failure: verify AKS OIDC issuer, federated identity issuer, audience, and exact subject system:serviceaccount:demo:hello-api.
- Key Vault 403: verify the managed identity client ID annotation and Key Vault Secrets User role assignment. Allow time for role assignment propagation.
- ImagePullBackOff: verify the ACR image tag exists and the AKS kubelet identity retains AcrPull.
- Secret not found: verify the secret name and vault URI.
- Network timeout: the development vault uses its public endpoint. Private endpoint routing is not included yet.

Do not install a second Helm release for hello-api while Argo CD manages the Application. To clean up, delete the Argo CD Application first and then the demo namespace as described in the GitOps runbook.
