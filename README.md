# Kaviont Platform

[![CI](https://github.com/mohamadjaafri/kaviont-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mohamadjaafri/kaviont-platform/actions/workflows/ci.yml)

**Cloud Infrastructure. Automation. Engineering.**

Kaviont is an independent engineering reference project for building a repeatable cloud-native platform on Microsoft Azure. It combines Terraform-managed infrastructure, AKS, federated workload identity, Key Vault, a containerized sample workload, an Entra ID-protected Terraform state backend, and Argo CD GitOps delivery.

> Status: early reference implementation. Kaviont is a working project name, not a cleared or registered product mark. This repository is an independent portfolio project and is not affiliated with any employer or customer.

## Engineering scope

- Modular Infrastructure as Code with Terraform.
- Separate Terraform bootstrap for a protected Azure Storage state backend.
- Azure Blob state with versioning, soft delete, native state locking, and Microsoft Entra ID authentication.
- Azure networking with dedicated AKS and reserved private-endpoint subnets.
- AKS with Azure RBAC, managed identity, OIDC, and Workload Identity.
- Azure CNI Overlay with Cilium network policy/data plane.
- Azure Container Registry with admin credentials disabled and scoped AcrPull assignment.
- Azure Key Vault with RBAC, soft delete, and purge protection.
- Dedicated workload managed identity with a federated credential bound to one Kubernetes service account.
- FastAPI sample workload using Azure Identity and Key Vault SDK without exposing secret values.
- Helm deployment with service account annotations, workload identity pod labels, health probes, resource limits, autoscaling, PodDisruptionBudget, and NetworkPolicy.
- Argo CD Application and restricted AppProject for Git-based reconciliation of the demo workload.
- GitHub Actions checks for both Terraform roots, Helm, Python tests, container build, and GitOps manifests.

## Architecture

The engineer pushes code to GitHub. GitHub Actions validates both Terraform roots, tests the API, builds the container, validates the Helm chart, and checks the Argo CD project/application configuration.

A dedicated bootstrap root provisions an Azure Storage account for Terraform state. Shared Key authorization is disabled. The state blob is protected with versioning and soft delete. Terraform accesses it through Microsoft Entra ID, while Azure Blob Storage provides native state locking.

The development Terraform root provisions the Azure resource group, virtual network, AKS, ACR, Key Vault, a dedicated hello-api managed identity, a federated identity credential, and a scoped Key Vault Secrets User assignment.

Argo CD runs inside AKS and watches the main branch of this repository. Its restricted AppProject permits only the Kaviont repository, the in-cluster demo namespace, and the resource kinds required by the hello-api Helm chart. The Application renders the chart with a generated, non-secret values file and reconciles the desired state through automated sync, pruning, and self-healing.

The Kubernetes service account in namespace demo is trusted by the federated identity credential. The workload identity webhook injects the projected token into the labelled pod. Azure Identity exchanges that token for a Microsoft Entra token. The API reads a demo secret from Key Vault and reports only whether it exists.

Detailed design: docs/architecture.md, ADR 0001-0004, docs/security-and-cost.md, and the runbooks under docs/runbooks/.

## Repository layout

- .github: CI and dependency updates
- charts/hello-api: Helm chart and GitOps values template
- gitops/argocd: AppProject, Application, and Kustomize entry point
- scripts: Terraform output renderer, Argo CD bootstrap, and GitOps validator
- infrastructure/terraform/bootstrap/state: remote state foundation
- infrastructure/terraform/environments/dev: development platform
- infrastructure/terraform/modules: reusable Terraform modules
- docs: architecture, ADRs, and runbooks
- workloads/hello-api: FastAPI service, tests, and Dockerfile
- Makefile: local validation commands

## Validate locally

Prerequisites: Terraform 1.11.x, Azure CLI, Helm, Docker, and Python 3.12.

From the repository root:

- make fmt-check
- make terraform-bootstrap-validate
- make terraform-validate
- make app-test
- make helm-check
- make gitops-check
- make image-build

These commands validate source and build a local image. They do not provision Azure resources or install Argo CD.

## Provision the development environment

1. Follow docs/runbooks/terraform-remote-state.md to create the dedicated state account and migrate both Terraform roots to Azure Blob state.
2. Authenticate with Azure CLI and select a non-production subscription.
3. Copy infrastructure/terraform/environments/dev/terraform.tfvars.example to terraform.tfvars.
4. Set a unique 4-8 character lowercase alphanumeric unique_suffix for ACR and Key Vault.
5. Replace the documentation-only API-server CIDR with your fixed public egress IP in /32 notation.
6. Run terraform validate and terraform plan -out=tfplan from infrastructure/terraform/environments/dev.
7. Review the plan, then run terraform apply tfplan.

## Deploy the sample workload

Follow docs/runbooks/argocd-gitops.md. It creates a non-production demo secret, builds and pushes the image to ACR, renders the environment-specific GitOps values from Terraform outputs, and bootstraps Argo CD.

The generated values file contains only the ACR login server, managed identity client ID, Key Vault URI, image tag, and secret name. Do not place secret material in Git.

## Clean up

Delete the Argo CD Application before deleting namespace demo so that the controller stops reconciling the workload. Follow the cleanup sequence in docs/runbooks/argocd-gitops.md, then destroy the development environment using the Terraform runbook.

Do not destroy the separate state bootstrap account while either Terraform root uses it. Terraform state and plan files must never be committed.

Key Vault uses soft delete and purge protection. A destroyed vault can remain recoverable and its name may not be immediately reusable.

## Security and operational boundaries

The state storage account uses Entra ID data-plane authorization and disables Shared Key access. Its public endpoint remains enabled in this development profile. The operator identity has Storage Blob Data Contributor on the dedicated state account.

The Argo CD AppProject restricts the application to this repository, the in-cluster demo namespace, and a small namespace-scoped resource allowlist. Argo CD does not provision Azure infrastructure or access Terraform state. The upstream non-HA installation is intended for learning, uses the built-in admin account initially, and is accessed through port forwarding. SSO, a managed ingress with valid TLS, and HA are not included.

The GitHub Actions workflow validates source code only. It does not authenticate to Azure, read remote state, or deploy resources. A production pipeline should use GitHub OIDC federation, protected environments, approval gates, and narrowly scoped state and deployment permissions.

The project does not yet implement private AKS/Key Vault/state endpoints, policy-as-code enforcement, image signing, secret rotation, centralized observability, or production HA. These are roadmap items, not current capabilities.

AKS nodes, disks, load balancers, registry storage, Key Vault operations, state storage, Argo CD and network egress can incur charges while the environment exists. Review current regional pricing and destroy unused development resources.

## Roadmap

- Private AKS API endpoint, private DNS, private ACR, Key Vault, and state connectivity.
- Key Vault CSI integration for file-based secret consumers.
- Managed Prometheus, Grafana dashboards, and OpenTelemetry.
- GitHub Actions deployment through OIDC with environment protection.
- Policy checks, image scanning, and container image signing.
- Argo CD SSO, ingress TLS, HA, and production hardening.

## Contributing and license

See CONTRIBUTING.md. The project is licensed under MIT. See LICENSE.

## Technical references

- Terraform azurerm backend: https://developer.hashicorp.com/terraform/language/backend/azurerm
- AzureRM Storage Account resource: https://registry.terraform.io/providers/hashicorp/azurerm/4.59.0/docs/resources/storage_account
- Microsoft Entra Workload ID on AKS: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- Key Vault RBAC guide: https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide
- Argo CD v3.6.1 release: https://github.com/argoproj/argo-cd/releases/tag/v3.6.1
- Argo CD Application specification: https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/
- Argo CD automated sync: https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/
