# Kaviont Engineering Platform

The engineering portal is served at /engineering and its API is rooted at /v1/engineering. The first release is read-only for connected source-control and Kubernetes systems. Template downloads are generated locally in memory. Repository creation, commits, deployments and cloud mutations are not exposed by this release.

## GitHub connection

Configure KAVIONT_GITHUB_TOKEN through the ignored local .env file or a Kubernetes Secret. Do not put tokens into Git, Helm values, image layers, logs or browser code.

For a fine-grained personal access token, limit repository access to the projects Kaviont should display. Grant read-only access to:
- Metadata
- Contents
- Actions
- Pull requests
- Issues
- Dependabot alerts
- Code scanning alerts

A GitHub App with narrowly scoped repository installation permissions is the preferred organization-level integration. The current client uses the GitHub REST API and does not need write permissions.

Optional settings:
- GITHUB_API_URL: HTTPS GitHub Enterprise or GitHub API base URL.
- KAVIONT_KNOWLEDGE_REPOSITORY: owner/name for Markdown documents displayed in the Knowledge Hub.

Start the Compose API with the optional token in your local .env file:

    cp .env.example .env
    # edit .env and set KAVIONT_GITHUB_TOKEN
    make dev-up

Open http://127.0.0.1:8080/engineering. The UI also works without a token and shows the missing integration state rather than failing application startup.

## Kubernetes runtime integration

The Helm chart defaults to no service-account token mount and no Kubernetes API permission. To enable the portal's read-only runtime view, set:

    platformInsights:
      kubernetes:
        enabled: true

The chart then:
- Enables the service-account token mount only for the selected release.
- Creates a Role and RoleBinding in the release namespace.
- Grants get/list/watch only on pods, services, events, deployments and replicasets.
- Does not grant access to Secrets, exec, logs, mutations or cluster-scoped resources.

For the local kind profile, this setting is enabled in values-local.yaml. The API validates the configured namespace and requires HTTPS for the Kubernetes API URL.

## Security workflow integration

The repository includes:
- CodeQL for Python and JavaScript source analysis.
- Trivy filesystem checks for vulnerabilities, misconfiguration and secrets, plus a CycloneDX SBOM artifact.
- Gitleaks secret scanning.
- OWASP Dependency-Check as a slower scheduled/manual SCA report.
- OWASP ZAP Baseline as a separately dispatched passive DAST workflow.

Other repositories can reuse the security workflow:

    jobs:
      security:
        uses: mohamadjaafri/kaviont-platform/.github/workflows/reusable-security.yml@main
        permissions:
          actions: read
          contents: read
          security-events: write
        with:
          run_dependency_check: false

Enable GitHub Code Scanning and ensure the workflow token has security-events: write for SARIF upload. Dependabot alerts require the feature to be enabled for the repository and the token to have Dependabot alerts read access.

Optionally set the repository or organization secret NVD_API_KEY to improve the NVD update rate for OWASP Dependency-Check. The expensive Dependency-Check job runs on the weekly schedule or when manually dispatched.

## OWASP classification

The portal exposes the OWASP Top 10:2025 categories and ASVS 5.0.0 reference. Where CodeQL/SARIF metadata includes a CWE tag, Kaviont applies a small, explicit CWE-to-Top-10 mapping. Dependabot findings are classified as software supply-chain findings.

The mapping is intentionally heuristic and incomplete. An unmapped finding is displayed as requiring manual review. Scanner output is not an ASVS assessment, penetration test, security certification or proof that the application is secure.

## DAST scope

OWASP ZAP Baseline can only be started manually. The operator must:
1. Confirm that they own the target or have written authorization.
2. Provide an HTTPS URL on port 443 without embedded credentials.
3. Add the exact hostname to the repository or organization variable DAST_ALLOWED_HOSTS.

The workflow rejects non-HTTPS URLs, unapproved hosts and private/loopback IP literals. This baseline workflow is passive and does not run an active attack scan. Use a dedicated test environment and keep the allowlist limited to explicitly authorized hosts.

## Service catalog, Cloud & IaC and self-service boundaries

The first service catalog derives service candidates from repository metadata and topics. Team owner, lifecycle and criticality remain unclassified until a service metadata contract is introduced.

The Cloud & IaC module discovers repositories that appear to contain Terraform, Bicep or infrastructure topics. Environment variable presence is shown separately from a verified provider connection. Azure, AWS and GCP inventory, policy compliance and cost APIs are not yet connected.

Self-service supports downloads of four starter archives: Python FastAPI service, Node.js service, Terraform module and Kubernetes Helm workload. The download does not create a GitHub repository, commit code, provision cloud resources or deploy a workload. Those write actions require separate identities, approvals and audit records.

## API surface

- GET /v1/engineering/status
- GET /v1/engineering/overview
- GET /v1/engineering/repositories
- GET /v1/engineering/repositories/{owner}/{repo}
- GET /v1/engineering/repositories/{owner}/{repo}/pipelines
- GET /v1/engineering/repositories/{owner}/{repo}/security
- GET /v1/engineering/security/frameworks
- GET /v1/engineering/services
- GET /v1/engineering/kubernetes
- GET /v1/engineering/cloud
- GET /v1/engineering/knowledge
- GET /v1/engineering/templates
- GET /v1/engineering/templates/{template_id}/download

The API never returns the configured GitHub token. Engineering API responses use Cache-Control: no-store.

## Access boundary

The initial portal is intended for local development or an internal-only network. The GitHub token is a shared server-side integration credential, so every caller who can reach the API can read the repository information permitted to that token. Do not expose /engineering or /v1/engineering through a public ingress until user authentication, authorization, tenant/repository scoping and audit logging are configured. Use an OIDC/SSO-aware reverse proxy or a first-party authentication layer before any shared or production deployment.
