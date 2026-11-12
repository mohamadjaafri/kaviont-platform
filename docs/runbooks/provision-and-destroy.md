# Runbook: provision and destroy the development platform

## Before provisioning

- Confirm the target Azure subscription and tenant.
- Confirm the operator identity can create the listed resources and role assignments.
- Check selected AKS VM SKU availability in the region.
- Select a globally unique ACR suffix.
- Set the API server allowlist to the operator's fixed public egress IP in CIDR notation.
- Review the expected cost for the selected region and VM size.

## Provision

```bash
az login
az account set --subscription <subscription-id>
export ARM_SUBSCRIPTION_ID=<subscription-id>

cp infrastructure/terraform/environments/dev/terraform.tfvars.example \
   infrastructure/terraform/environments/dev/terraform.tfvars
# Edit unique_suffix and api_server_authorized_ip_ranges.

cd infrastructure/terraform/environments/dev
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

If the first apply fails immediately after a role assignment is created, inspect the Azure error and role propagation state before retrying. Do not apply repeatedly without understanding the failure.

## Connect

```bash
RESOURCE_GROUP=$(terraform output -raw resource_group_name)
AKS_NAME=$(terraform output -raw aks_cluster_name)
ACR_NAME=$(terraform output -raw acr_name)
ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)

az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME"
kubectl get nodes
az acr login --name "$ACR_NAME"
```

## Deploy sample API

```bash
docker build -t "$ACR_LOGIN_SERVER/hello-api:0.1.0" ../../../../workloads/hello-api
docker push "$ACR_LOGIN_SERVER/hello-api:0.1.0"
helm upgrade --install hello-api ../../../../charts/hello-api \
  --namespace demo --create-namespace \
  --set image.repository="$ACR_LOGIN_SERVER/hello-api" \
  --set image.tag=0.1.0
kubectl rollout status deployment/hello-api -n demo
```

## Destroy

```bash
helm uninstall hello-api -n demo || true
kubectl delete namespace demo --ignore-not-found
cd infrastructure/terraform/environments/dev
terraform plan -destroy -out=destroy.tfplan
terraform apply destroy.tfplan
```

Retain or delete the Terraform state according to your own state-management policy. Never commit state or plan files.
