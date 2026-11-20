# Kaviont Home Server

Run Kaviont on your own always-on PC with Docker Compose. No cloud VM, Kubernetes cluster, public IP or router port-forwarding is required.

## What runs on the PC

The dedicated `compose.home.yaml` stack runs:
- FastAPI, including the Engineering Portal and Market Dashboard.
- PostgreSQL with a persistent named volume for market history.
- The market-data worker.

This is separate from the hot-reload development profile. The home stack uses the built runtime image, production settings, restart policies and no bind-mounted source tree. The API is published only on `127.0.0.1:8080`. PostgreSQL has no published host port.

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

   Put the generated value in `.env.home` as `POSTGRES_PASSWORD`. Keep `.env.home` private and never commit it. Optionally set `KAVIONT_GITHUB_TOKEN` to a read-only token for the repositories Kaviont should display.

5. Start the home stack:

   ```bash
   make home-up
   make home-status
   ```

6. Verify the service on the PC at `http://127.0.0.1:8080/engineering/` and `http://127.0.0.1:8080/market`.

The database is stored in the Docker named volume `kaviont-home_market-data-db` (Compose project name may affect the exact prefix). `make home-down` stops containers but preserves this volume. Do not run `docker compose down --volumes` unless you intentionally want to delete the stored market history.

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
- Keep Tailscale membership limited to your own devices and users you trust. Anyone with tailnet access to this service can use the Engineering Portal with the permissions of the configured GitHub token.
- The first release of the Engineering Portal is read-only. Do not expose it publicly or switch to Tailscale Funnel. Add user-level authentication, authorization and audit logging before sharing it beyond your private devices.
- Keep backups of the Docker volume. A named volume survives container recreation, but it is not a backup against disk failure.

## Operations

```bash
make home-logs
make home-status
make home-down
make home-up
```

Use `git pull` to update the repository, then run `make home-up` to rebuild and recreate the application containers. PostgreSQL data remains in the named volume.
