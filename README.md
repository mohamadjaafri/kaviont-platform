# Kaviont Platform

[![CI](https://github.com/mohamadjaafri/kaviont-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mohamadjaafri/kaviont-platform/actions/workflows/ci.yml)

**Cloud Infrastructure. Automation. Engineering.**

Kaviont is an independent engineering reference project for building a repeatable cloud-native platform on Microsoft Azure. It combines Terraform-managed infrastructure, AKS, federated workload identity, Key Vault, and a containerized sample workload.

> Status: early reference implementation. Kaviont is a working project name, not a cleared or registered product mark. This repository is an independent portfolio project and is not affiliated with any employer or customer.

## Engineering scope

- Modular Infrastructure as Code with Terraform.
- Azure networking with dedicated AKS and reserved private-endpoint subnets.
- AKS with Azure RBAC, managed identity, OIDC, and Workload Identity.
- Azure CNI Overlay with Cilium network policy/data plane.
- Azure Container Registry with admin credentials disabled and scoped AcrPull assignment.
- Azure Key Vault with RBAC, soft delete, and purge protection.
- Dedicated workload managed identity with a federated credential bound to one Kubernetes service account.
- FastAPI sample workload using Azure Identity and Key Vault SDK without exposing secret values.
- Helm deployment with service account annotations, workload identity pod labels, health probes, resource limits, autoscaling, PodDisruptionBudget, and NetworkPolicy.
- GitHub Actions checks for Terraform, Helm, Python tests, and image builds.

## Architecture

The engineer pushes code to GitHub. GitHub Actions validates Terraform, tests the API, builds the container, and validates the Helm chart.

Terraform provisions the Azure resource group, virtual network, AKS, ACR, Key Vault, a dedicated hello-api managed identity, a federated identity credential, and a scoped Key Vault Secrets User assignment.

The Kubernetes service account in namespace demo is trusted by the federated identity credential. The workload identity webhook injects the projected token into the labelled pod. Azure Identity exchanges that token for a Microsoft Entra token. The API reads a demo secret from Key Vault and reports only whether it exists.

Detailed design: docs/architecture.md, ADR 0001, ADR 0002, docs/security-and-cost.md, docs/runbooks/provision-and-destroy.md, and docs/runbooks/workload-identity-and-key-vault.md.

## Repository layout

- .github: CI and dependency updates
- charts/hello-api: Helm chart
- infrastructure/terraform: reusable Terraform modules and dev environment
- docs: architecture, ADRs, and runbooks
- workloads/hello-api: FastAPI service, tests, and Dockerfile
- Makefile: local validation commands

## Validate locally

Prerequisites: Terraform 1.11.x, Azure CLI, Helm 3.x, Docker, and Python 3.12.

From the repository root:

- make fmt-check
- make terraform-validate
- make app-test
- make helm-check
- make image-build

These commands validate the source and build a local image. They do not provision Azure resources.

## Provision the development environment

1. Authenticate with Azure, select a non-production subscription, and export ARM_SUBSCRIPTION_ID.
2. Copy infrastructure/terraform/environments/dev/terraform.tfvars.example to terraform.tfvars.
3. Set a unique 4-8 character lowercase alphanumeric unique_suffix for ACR and Key Vault.
4. Replace the documentation-only API-server CIDR with your fixed public egress IP in /32 notation.
5. Run terraform init, terraform validate, and terraform plan -out=tfplan from infrastructure/terraform/environments/dev.
6. Review the plan, then run terraform apply tfplan.
7. Connect to AKS using the resource group and cluster name outputs.

## Deploy the sample workload

Follow docs/runbooks/workload-identity-and-key-vault.md. It creates a demo secret without printing its value, builds and pushes the image, and deploys the Helm chart with federated identity enabled.

## Clean up

Uninstall the Helm release and remove the demo namespace before destroying the Terraform environment. Review the destroy plan before confirming. Terraform state and plan files must never be committed.

Key Vault uses soft delete and purge protection. A destroyed vault can remain recoverable and its name may not be immediately reusable.

## Security and operational boundaries

The project demonstrates workload identity federation and read-only secret access, but it does not yet implement private AKS/Key Vault endpoints, remote Terraform state, policy-as-code enforcement, image signing, secret rotation, or production HA. These are roadmap items, not current capabilities.

AKS nodes, disks, load balancers, registry storage, Key Vault operations, and network egress can incur charges while the environment exists. Review current regional pricing and destroy unused environments.

## Roadmap

- Remote Terraform state in Azure Storage with Entra ID authentication and locking.
- Private AKS API endpoint, private DNS, private ACR and Key Vault connectivity.
- Key Vault CSI integration for file-based secret consumers.
- Managed Prometheus, Grafana dashboards, and OpenTelemetry.
- GitOps bootstrap with Argo CD.
- Policy checks, image scanning, and container image signing.

## Contributing and license

See CONTRIBUTING.md. The project is licensed under MIT. See LICENSE.

## Technical references

- AzureRM Key Vault resource: https://registry.terraform.io/providers/hashicorp/azurerm/4.59.0/docs/resources/key_vault
- AzureRM federated identity credential: https://registry.terraform.io/providers/hashicorp/azurerm/4.59.0/docs/resources/federated_identity_credential
- Microsoft Entra Workload ID on AKS: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- Key Vault RBAC guide: https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide
- Provision AKS with Terraform: https://developer.hashicorp.com/terraform/tutorials/kubernetes/aks
