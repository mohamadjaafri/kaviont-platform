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
- Argo CD Application and restricted AppProject for Git-based reconciliation of the Azure workload.
- Docker Compose development profile with source hot reload and containerized tests.
- Single-node kind profile with a separate restricted local Argo CD Application.
- Multi-stage container build with BuildKit dependency caching and distinct runtime/test targets.
- Optional local operations stack with OpenTelemetry, Prometheus, Tempo, Grafana, Blackbox Exporter, Alertmanager, Mailpit, a localhost-only Adminer database UI, and PostgreSQL exporter monitoring.
- Dedicated Kraken market-data worker with PostgreSQL persistence, a singleton advisory lock, latest-snapshot API reads, and historical ticker storage.
- Rolling 30-day 99.9% request availability objective, error-budget recording rules, golden-signal alerts, and local email notification tests.
- GitHub Actions checks for both Terraform roots, Helm, Python tests, container build, Prometheus rules, Alertmanager config, and GitOps manifests.

## Architecture

The engineer pushes code to GitHub. GitHub Actions validates both Terraform roots, tests the API, builds the container, validates the Helm chart, and checks the Argo CD project/application configuration.

A dedicated bootstrap root provisions an Azure Storage account for Terraform state. Shared Key authorization is disabled. The state blob is protected with versioning and soft delete. Terraform accesses it through Microsoft Entra ID, while Azure Blob Storage provides native state locking.

The development Terraform root provisions the Azure resource group, virtual network, AKS, ACR, Key Vault, a dedicated hello-api managed identity, a federated identity credential, and a scoped Key Vault Secrets User assignment.

Argo CD runs inside AKS and watches the main branch of this repository for the Azure demo workload. A separate optional local profile uses kind and its own restricted Argo CD project in namespace kaviont-local. The local Application uses a preloaded Docker image and local Helm values; it does not use ACR, Workload Identity, or Key Vault.

Docker Compose provides the faster application loop: it mounts the API source read-only and runs Uvicorn with reload. The test target runs pytest inside a container. BuildKit caches dependency installation independently from source changes.

The Kubernetes service account in namespace demo is trusted by the federated identity credential. The workload identity webhook injects the projected token into the labelled pod. Azure Identity exchanges that token for a Microsoft Entra token. The API reads a demo secret from Key Vault and reports only whether it exists.

Detailed design: docs/architecture.md, ADR 0001-0006, docs/security-and-cost.md, and the runbooks under docs/runbooks/.

## Repository layout

- .github: CI and dependency updates
- charts/hello-api: Helm chart and GitOps values template
- gitops/argocd: Azure and local AppProjects, Applications, and Kustomize entry points
- kind: single-node local Kubernetes cluster configuration
- compose.yaml: containerized API, market-data worker, PostgreSQL, Adminer, test, and operations profiles
- db/init: initial PostgreSQL schema for ticker history and worker status
- observability: Collector, Prometheus, SLO and PostgreSQL rules, Blackbox Exporter, Alertmanager, Tempo, and Grafana dashboards
- scripts: Terraform output renderer, Argo CD bootstrap, local cluster lifecycle, and GitOps validator
- infrastructure/terraform/bootstrap/state: remote state foundation
- infrastructure/terraform/environments/dev: development platform
- infrastructure/terraform/modules: reusable Terraform modules
- docs: architecture, ADRs, and runbooks
- workloads/hello-api: FastAPI service, tests, and Dockerfile
- Makefile: local validation commands

## Local-first development

The fastest loop uses Docker Compose. You need Docker Engine and Docker Compose v2, but no host Python installation and no Azure subscription.

    make dev-up
    make container-test
    make dev-logs
    make dev-down

The API listens on http://127.0.0.1:8080 and reloads when you change Python source. The test runner is a separate container target. Dependencies are cached by BuildKit.

For Kubernetes and GitOps integration, install kind, kubectl, and OpenSSL, then follow docs/runbooks/local-development.md:

    make local-up
    make local-status
    make local-forward
    make local-build
    make local-down

The kind cluster has one node. The application image is loaded directly into that node, never pushed to ACR. The local Argo CD Application and Azure Argo CD Application use separate projects, namespaces, and values files.

## Integrated local Kubernetes observability

Start the Kubernetes/GitOps environment and the observability stack together:

    make platform-up

The command creates or reuses the kind cluster, deploys the hello-api and an OpenTelemetry Collector through Argo CD, starts PostgreSQL, Adminer, Prometheus/Grafana/Alertmanager/Mailpit, and the other local operations services with Docker Compose, and connects Prometheus and Blackbox Exporter to the kind Docker network. Prometheus scrapes OTLP metrics from the Kubernetes workload and blackbox-probes its readiness endpoint. The local API is exposed through NodePort 30081 inside the kind Docker network, and the collector's Prometheus endpoint through NodePort 30089.

Use the combined lifecycle commands:

    make platform-status
    make platform-down

Adminer is available at http://127.0.0.1:8085. It connects to the Compose PostgreSQL service over the internal Compose network and its web port is bound to localhost only. Use System `PostgreSQL`, Server `postgres`, Username `kaviont`, Database `kaviont`, and the configured `POSTGRES_PASSWORD` (default: `kaviont-local-only`). To start only PostgreSQL and its UI without the rest of the operations stack, run `make database-ui`; stop only the UI with `make database-ui-down`.

PostgreSQL monitoring uses the Prometheus Community exporter at version `v0.20.1`. A one-shot Compose bootstrap creates a dedicated `postgres_exporter` role and grants PostgreSQL's built-in `pg_monitor` role. The exporter connects to the internal PostgreSQL service and does not publish port 9187 to the host. Configure its local-only password through `POSTGRES_EXPORTER_PASSWORD` in your ignored `.env` file (default: `kaviont-exporter-local-only`). The **Kaviont - PostgreSQL Reliability** Grafana dashboard shows connection utilization, database size, transactions, cache hit ratio, locks, deadlocks, and long-running transactions. Prometheus alerts cover exporter/database availability, connection saturation, deadlocks, and long-running transactions. See `docs/runbooks/postgresql-monitoring.md`.

The integrated dashboard includes the Kubernetes API readiness, request rate, and p95 latency alongside the existing local operations panels. The kind collector sends Kubernetes application metrics to Prometheus; its traces go to the collector debug exporter rather than the Compose Tempo instance. The existing Compose application continues to export traces to Tempo.

Use `make local-forward` in a separate terminal when you need to call the Kubernetes API from the host at http://127.0.0.1:8081. `make observability-up` and `make local-up` remain available independently.

## Local operations dashboard

Start the optional telemetry and operations stack:

    make observability-up

The dedicated market-data worker fetches the configured Kraken ticker immediately and refreshes it every 60 seconds by default. It writes each successful snapshot and its worker state to PostgreSQL. The API reads the latest persisted snapshot, so API replicas do not poll Kraken and share the same data. Check worker status at http://127.0.0.1:8080/v1/market/kraken/status and read the latest snapshot at http://127.0.0.1:8080/v1/market/kraken/ticker.

Open the provisioned **Kaviont - Operations Overview**, **Kaviont - Financial Data Reliability**, and **Kaviont - PostgreSQL Reliability** dashboards in Grafana at http://127.0.0.1:3000 (local default: admin / admin). The operations dashboard includes the rolling 30-day availability SLO, remaining error budget, request rate, 5xx ratio, p95 latency, readiness probe, API process CPU/RAM, and Tempo traces. The PostgreSQL dashboard provides a separate database-level view.

Configure the polling interval with KRAKEN_POLL_INTERVAL_SECONDS and market pair with KRAKEN_MARKET_PAIR. The worker holds a PostgreSQL session-level advisory lock, preventing overlapping worker instances from polling at the same time. PostgreSQL keeps the ticker history in the named market-data-db volume. Adminer provides a browser-based view of this database at http://127.0.0.1:8085. The local Compose credentials are development-only.

Operational alerts are evaluated by Prometheus and routed through Alertmanager. Mailpit catches notification emails locally at http://127.0.0.1:8025, without sending them externally. Prometheus is at http://127.0.0.1:9090 and Alertmanager is at http://127.0.0.1:9093.

For a controlled local alert demonstration, generate HTTP 500 responses using:

    for i in $(seq 1 40); do
      curl -sS -o /dev/null http://127.0.0.1:8080/__test__/error
    done

The fault-injection route is registered only in local/test environments. See docs/runbooks/observability-local.md for setup, expected alert timing, and cleanup. This is a local learning profile, not production monitoring.

## Validate infrastructure and charts

Terraform and Azure CLI are needed only for the Azure infrastructure workflow. From the repository root:

- make fmt-check
- make terraform-bootstrap-validate
- make terraform-validate
- make app-test
- make helm-check
- make gitops-check
- make image-build

These commands validate source and build a local image. They do not provision Azure resources. See docs/runbooks/local-development.md for the complete container-first local workflow.

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

The local operations profile binds its published ports to localhost and uses Mailpit as a mail sink. The PostgreSQL exporter is accessible only on the Compose network and uses a dedicated `pg_monitor` role. It is not production monitoring: Prometheus, Tempo, Alertmanager, Mailpit, and Blackbox Exporter have no authentication or TLS. Process CPU and memory metrics describe hello-api only, not the entire Docker host or an AKS cluster. The 99.9% objective is an example request-based SLO, not a contractual SLA.

The project does not yet implement private AKS/Key Vault/state endpoints, policy-as-code enforcement, image signing, secret rotation, centralized production observability, or production HA. These are roadmap items, not current capabilities.

AKS nodes, disks, load balancers, registry storage, Key Vault operations, state storage, Argo CD and network egress can incur charges while the environment exists. Review current regional pricing and destroy unused development resources.

## Roadmap

- Private AKS API endpoint, private DNS, private ACR, Key Vault, and state connectivity.
- Key Vault CSI integration for file-based secret consumers.
- AKS deployment of the OpenTelemetry Collector and managed observability backends.
- GitHub Actions deployment through OIDC with environment protection.
- Policy checks, image scanning, and container image signing.
- Argo CD SSO, ingress TLS, HA, and production hardening.

## Contributing and license

See CONTRIBUTING.md. The project is licensed under MIT. See LICENSE.

## Technical references

- Terraform azurerm backend: https://developer.hashicorp.com/terraform/language/backend/azurerm
- Microsoft Entra Workload ID on AKS: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- Key Vault RBAC guide: https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide
- Argo CD Application specification: https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/
- Argo CD automated sync: https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/
