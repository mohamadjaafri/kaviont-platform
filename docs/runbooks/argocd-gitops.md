# Runbook: deploy hello-api with Argo CD GitOps

This runbook assumes the Azure development environment has been provisioned, the AKS cluster is reachable, and the sample image has been pushed to the project ACR.

## Operating model

Terraform owns Azure infrastructure. Argo CD owns the hello-api Kubernetes resources in the demo namespace. The source of truth for the workload is the main branch of this Git repository.

The Application tracks charts/hello-api and loads charts/hello-api/values-gitops.yaml. Automated sync, pruning, and self-healing are enabled. Do not manage the same hello-api resources with a separate Helm release or kubectl apply after Argo CD takes ownership.

The Argo CD installation is pinned to upstream release v3.6.1 and uses the upstream non-HA installation manifest. This is a learning/development profile, not an HA or hardened production Argo CD installation.

## Prerequisites

- Azure development resources already provisioned and remote Terraform state configured.
- kubectl connected to the intended AKS cluster.
- Docker and Azure CLI authenticated to the project subscription.
- Python 3.12 for the configuration helper.
- An administrator or operator with permission to create the demo secret in Key Vault.
- No existing Helm release named hello-api managing the same namespace resources.

## 1. Create the demo Key Vault secret

The API checks whether the configured demo secret exists. It never returns the value.

From the repository root, set the vault name and create a disposable non-production secret:

```bash
KEY_VAULT_NAME="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw key_vault_name)"

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "platform-demo-token" \
  --value "$(openssl rand -hex 32)" \
  --query id --output tsv
```

The command prints only the secret resource ID, not its value. Do not use a real credential.

## 2. Build and push the image to ACR

Read the registry login server and name from Terraform outputs:

```bash
ACR_NAME="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw acr_name)"
ACR_LOGIN_SERVER="$(terraform -chdir=infrastructure/terraform/environments/dev output -raw acr_login_server)"

az acr login --name "$ACR_NAME"
docker build -t "$ACR_LOGIN_SERVER/hello-api:0.2.0" workloads/hello-api
docker push "$ACR_LOGIN_SERVER/hello-api:0.2.0"
```

The AKS kubelet identity already has AcrPull on the project registry. Do not put a registry password into a Kubernetes Secret.

## 3. Generate the environment-specific GitOps values

Run:

```bash
python scripts/configure-gitops.py
```

The helper reads the ACR login server, hello-api managed identity client ID, and Key Vault URI from the Terraform outputs. It generates charts/hello-api/values-gitops.yaml from the checked-in example template.

The generated file contains non-secret infrastructure identifiers only. It must not contain a Key Vault secret value, password, token, or client secret.

Review the generated values and commit them to the repository:

```bash
git checkout -b config/kaviont-dev-gitops
git add charts/hello-api/values-gitops.yaml
git commit -m "chore(gitops): configure dev workload values"
git push -u origin config/kaviont-dev-gitops
```

Open and merge a pull request into main. The Argo CD Application tracks main, so it will consume the merged values file.

The Argo CD bootstrap script intentionally refuses to run while the values file is missing or still contains replacement markers.

## 4. Install Argo CD and register the application

Connect kubectl to the correct AKS cluster and check the active context:

```bash
kubectl config current-context
kubectl get nodes
```

After the configuration pull request is merged, bootstrap Argo CD:

```bash
bash scripts/bootstrap-argocd.sh
```

The script installs the upstream Argo CD v3.6.1 non-HA manifest, waits for the Application CRDs and API server, then applies the restricted Kaviont AppProject and hello-api Application.

The app project allows:
- One source repository: this Kaviont GitHub repository.
- One destination: the in-cluster demo namespace.
- Only the namespace-scoped resource kinds rendered by the hello-api Helm chart.
- No cluster-scoped resources.

## 5. Access the Argo CD UI

Use port forwarding rather than exposing the Argo CD server publicly:

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Open https://localhost:8080. The initial username is admin. Retrieve the one-time initial password locally:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
echo
```

Change the initial password immediately after the first login. Do not copy it into Git, issue comments, CI logs, or chat. For a longer-lived environment, configure SSO, disable the built-in admin account where appropriate, and use a managed ingress with valid TLS.

## 6. Verify reconciliation

Check the Application and workload:

```bash
kubectl get applications -n argocd
kubectl get appproject kaviont-dev -n argocd
kubectl get pods,svc,hpa,pdb,networkpolicy -n demo
kubectl rollout status deployment/hello-api -n demo
```

The Application should converge to Synced and Healthy. The pod template must carry the azure.workload.identity/use label, and the hello-api service account must carry the managed identity client ID annotation.

Verify the API without exposing the demo secret:

```bash
kubectl port-forward svc/hello-api -n demo 8081:80
curl --fail http://127.0.0.1:8081/v1/secret-status
```

Expected response:

```json
{"mode":"azure-key-vault","secret_configured":true}
```

## 7. Change and rollback workflow

- Change the chart or GitOps values through a pull request.
- Merge only after CI passes and the change is reviewed.
- Argo CD detects the new main revision and reconciles the cluster.
- Revert the Git commit to restore the previous desired state.
- Do not use kubectl edit or a second Helm release to manage Argo-owned resources.

Automated pruning is enabled. Removing a resource from the chart can delete it from the cluster. The application project and chart scope are intentionally restricted to the demo workload.

## 8. Troubleshooting

- Application cannot fetch the repository: check repository URL, public visibility, target revision, and GitHub availability.
- Helm values file not found: verify charts/hello-api/values-gitops.yaml is committed to main.
- ImagePullBackOff: verify the image tag exists in ACR and the AKS kubelet identity retains AcrPull.
- Workload identity token exchange failure: verify the service account annotation, pod label, AKS OIDC issuer, federated credential subject, and audience.
- Key Vault 403: verify the hello-api identity has Key Vault Secrets User on the intended vault and allow for role assignment propagation.
- Application is OutOfSync after a manual change: this is expected with self-heal enabled. Revert the change in Git instead.

## 9. Clean up

Delete the Argo CD Application first so it stops reconciling the demo workload:

```bash
kubectl delete application hello-api -n argocd
kubectl delete namespace demo
```

Remove Argo CD only after confirming no other applications use it:

```bash
kubectl delete -k gitops/argocd
kubectl delete namespace argocd
```

Then follow the Terraform destroy runbook for the development environment. Never destroy the separate Terraform state account as part of routine AKS cleanup.
