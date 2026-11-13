# Runbook: local-first development

Kaviont has two container-first local workflows. Neither provisions Azure resources or creates Azure charges.

- **Compose loop:** the quickest API development and test cycle. It runs the application and test runner in containers. Source changes are mounted read-only and Uvicorn reloads the API.
- **kind + Argo CD:** a single-node local Kubernetes cluster for deployment, Helm rendering, image loading, and GitOps reconciliation. kind nodes are Docker containers.

The local profile is deliberately separate from the AKS profile. It does not emulate Azure networking, Microsoft Entra Workload Identity, ACR, or Key Vault.

## Prerequisites

For the Compose workflow:
- Docker Desktop with the WSL 2 backend on Windows, or Docker Engine on Linux.
- Docker Compose v2.

For the Kubernetes workflow, also install:
- kind.
- kubectl.
- OpenSSL.

On Windows, run the commands from a WSL 2 distribution with Docker Desktop WSL integration enabled. Keep the repository in the WSL filesystem for fast bind mounts. The CLI tools are clients on the developer machine; the API, test runner, local Kubernetes nodes, and Argo CD run as containers.

## 1. Fast API loop with Compose

Start the API:

```bash
make dev-up
```

The API is available at http://127.0.0.1:8080. The source folder is mounted read-only into the container, and Uvicorn reloads when you change Python files.

Useful checks:

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/readyz
curl --fail http://127.0.0.1:8080/v1/secret-status
```

Run the complete API test suite inside its dedicated test image:

```bash
make container-test
```

Stop the Compose service:

```bash
make dev-down
```

The Dockerfile uses a cached dependency layer and separate `runtime` and `test` targets. A code-only change does not reinstall Python dependencies. The runtime image does not contain pytest or the development dependencies.

## 2. Local Kubernetes and GitOps

The local Kubernetes workflow needs a working Docker engine. It creates one control-plane node to keep the resource footprint low.

After the local development changes have reached the repository's `main` branch, run:

```bash
make local-up
```

The script:
1. Creates or reuses the `kaviont-local` kind cluster.
2. Builds `kaviont/hello-api:local` and loads it directly into the kind node. The image is not pushed to a registry.
3. Creates the `argocd` and `kaviont-local` namespaces.
4. Creates a random, throwaway Kubernetes Secret for the local-only secret-presence demo.
5. Installs the same pinned Argo CD version used by the AKS profile.
6. Registers a restricted local AppProject and Application.

The local Application reads `charts/hello-api/values-local.yaml` from the `main` branch and deploys to namespace `kaviont-local`. It uses `imagePullPolicy: Never`, so Kubernetes must use the image loaded by kind. It does not contact ACR or Key Vault.

Check the deployment:

```bash
make local-status
kubectl --context kind-kaviont-local get applications -n argocd
kubectl --context kind-kaviont-local get pods,svc,hpa,pdb,networkpolicy -n kaviont-local
```

Forward the API to localhost:

```bash
make local-forward
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8081/healthz
curl --fail http://127.0.0.1:8081/v1/secret-status
```

The local secret endpoint reports only whether the ephemeral value is present. It never returns the value. This local Kubernetes Secret is a test fixture, not a replacement for Azure Key Vault.

## 3. Rebuild after application changes

For the fast feedback loop, Compose reloads Python source automatically.

For the local Kubernetes image:

```bash
make local-build
```

This rebuilds the runtime image, imports it into kind, and restarts the local Deployment. The tag remains `local` and the pull policy remains `Never`, avoiding a registry lookup.

Changes to the Helm chart or the local values file are reconciled by Argo CD only after they are committed and pushed to the branch watched by the local Application. The checked-in Application tracks `main` to keep the shared setup deterministic.

## 4. Resource and platform boundaries

- Compose is the default loop for code changes and unit tests. Do not start kind unless you need Kubernetes behavior.
- kind uses one node. It does not represent AKS multi-node availability or Azure networking.
- HPA is disabled locally because the minimal kind cluster does not install metrics-server.
- NetworkPolicy creation is disabled in the local values because kind's default CNI does not enforce NetworkPolicy. The Azure profile retains its network policy configuration.
- Workload Identity is disabled locally. Azure identity federation must be validated in AKS.
- Local secret material is random and disposable. Never use a real credential or commit a populated `.env` file.
- The Argo CD installation is the repository's non-HA learning profile, not a production configuration.

## 5. Clean up

Stop the fast Compose loop:

```bash
make dev-down
```

Delete the local Kubernetes cluster and its ephemeral secret:

```bash
make local-down
```

The Azure Terraform environments and the separate Terraform state account are not touched by these commands.
