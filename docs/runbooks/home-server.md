# Kaviont Home Server

Run Kaviont on your own always-on PC with Docker Compose. No cloud VM, Kubernetes cluster, public IP or router port-forwarding is required.

## What runs on the PC

The dedicated `compose.home.yaml` stack runs:
- FastAPI, including the Engineering Portal and Market Dashboard.
- PostgreSQL with a persistent named volume for market history.
- The market-data worker.

This is separate from the hot-reload development profile. The home stack uses the built runtime image, production settings, restart policies and no bind-mounted source tree. The API is published only on `127.0.0.1:8080`. PostgreSQL has no published host port. The Engineering Portal authenticates requests using the identity headers added by Tailscale Serve. Its default role is read-only.

## First-time setup

1. Install Docker Desktop (Windows/macOS) or Docker Engine with the Compose plugin (Linux).
2. Clone the repository on the home PC and open a terminal in the repository root.
3. Create the home-server environment file:

   ```bash
   cp .env.home.example .env.home
   ```

4. Generate a strong database password:

   ```bash
   openssl rand -hex 32
   ```

   Put the generated value in `.env.home` as `POSTGRES_PASSWORD`. Keep `.env.home` private and never commit it. Set `KAVIONT_ADMIN_USERS` to your exact Tailscale login email to enable write operations such as managing price alerts. Leave it empty for read-only access. Optionally set `KAVIONT_GITHUB_TOKEN` to a read-only token for the repositories Kaviont should display.

5. Start the home stack:

   ```bash
   make home-up
   make home-status
   ```

6. Verify the service on the PC at `http://127.0.0.1:8080/engineering/` and `http://127.0.0.1:8080/market`.

The database is stored in the Docker named volume `kaviont-home_market-data-db` (Compose project name may affect the exact prefix). `make home-down` stops containers but preserves this volume. Do not run `docker compose down --volumes` unless you intentionally want to delete the stored market history.

## Kubernetes read-only connection

The home Compose API can query one Kubernetes namespace using a dedicated service account. This is separate from the in-cluster service-account mode used by the kind/AKS Helm deployment.

1. Apply the namespace-scoped read-only account:

   ```bash
   kubectl apply -f kubernetes/readonly-reader.yaml
   ```

2. Create the local secret directory and export the cluster CA and a short-lived service-account token:

   ```bash
   mkdir -p .kaviont-secrets/kubernetes
   kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 --decode > .kaviont-secrets/kubernetes/ca.crt
   kubectl -n default create token kaviont-reader --duration=24h > .kaviont-secrets/kubernetes/token
   ```

3. Set `KUBERNETES_API_URL` in `.env.home` to the HTTPS API endpoint reachable from inside the Kaviont container. Do not use `127.0.0.1` unless the API is actually reachable at that address from the container. Keep TLS verification enabled. Set `KAVIONT_KUBERNETES_NAMESPACE` to the namespace bound to the Role.

4. Restart the stack with `make home-up`. Check the Kubernetes module for Deployments, Pod readiness, restarts, events and rollout status.

The sample Role grants only get/list/watch on Pods, Services, Events, Deployments and ReplicaSets in namespace `default`. Apply a separately reviewed Role/RoleBinding in another namespace when you need to inspect it. Tokens issued by `kubectl create token` expire according to cluster policy. Renew the token file and restart the API container when it expires. The Kubernetes CA and token live under the ignored `.kaviont-secrets` directory.

## Private HTTPS access from an iPhone

Use Tailscale to connect the PC and iPhone to the same private tailnet. The free Personal plan is suitable for an individual home setup.

1. Install Tailscale on the home PC and iPhone and sign in to the same tailnet.
2. On the PC, ensure the Tailscale device is connected and enable HTTPS certificates for the tailnet if prompted.
3. Start the private HTTPS proxy to the loopback-only API:

   ```bash
   tailscale serve --bg 8080
   tailscale serve status
   ```

4. Tailscale prints a private HTTPS URL similar to `https://home-pc.example.ts.net`. Open `https://home-pc.example.ts.net/engineering/` in Safari on the iPhone.
5. In Safari, choose Share > Add to Home Screen.

The URL is reachable only from devices connected to your tailnet. Tailscale Serve terminates HTTPS and proxies to the PC's local port. Do not enable Tailscale Funnel, configure router port forwarding, or publish port 8080 to the internet for this private setup.

The PC must stay powered on, connected to the internet, and running Docker and Tailscale while you use Kaviont remotely. Configure Docker Desktop and Tailscale to start with the PC, and prevent sleep while hosting.

## Mobile/offline behaviour

The Engineering Portal is installable as a Progressive Web App. Its service worker may cache the HTML and static shell assets only. Engineering API responses under `/v1/` are always requested from the live server and are never cached, so GitHub, security and Kubernetes data are not shown as fresh when the PC is offline. Offline mode is limited to the cached app shell.

## Security boundaries

- Keep `.env.home` out of Git. The GitHub token stays inside the API container and is never sent to browser JavaScript.
- The API and database are not published on public interfaces. Tailscale is the only remote access path in this guide.
- Keep Tailscale membership limited to your own devices and users you trust. Only authenticated Tailscale users can reach the portal through Serve. Set `KAVIONT_READER_USERS` to restrict readers and `KAVIONT_ADMIN_USERS` to grant write access. Without an admin entry, all authenticated users remain read-only. Audit records are written as structured JSON to the API container logs. The API listens only on loopback, because the backend trusts the identity headers that Tailscale Serve adds and strips from untrusted requests.
- Do not expose the portal publicly or switch to Tailscale Funnel. Tailscale Serve is the current SSO boundary. Audit logs record the authenticated identity, role, route, method, status and request ID without query strings or credentials.
- Keep backups of the Docker volume. A named volume survives container recreation, but it is not a backup against disk failure.

## Cloud inventory and costs

Optional read-only cloud connectors use credentials mounted into the API container or supplied by environment variables:

- Azure: use a dedicated service principal with Reader and Cost Management Reader roles on the target subscription.
- AWS: mount an AWS shared credentials/config file with read-only Resource Groups Tagging API and Cost Explorer permissions. The inventory lists tagged resources only.
- Google Cloud: mount an Application Default Credentials service-account file with Cloud Asset Viewer. Cost reporting additionally requires a configured BigQuery billing export table and query permission.

Set the matching variables in `.env.home`. Provider connections are independent. A provider with missing credentials remains disconnected and does not block the portal. Do not grant deployment, IAM administration or resource mutation permissions to these identities.

## Operations

```bash
make home-logs
make home-status
make home-down
make home-up
```

Use `git pull` to update the repository, then run `make home-up` to rebuild and recreate the application containers. PostgreSQL data remains in the named volume.
