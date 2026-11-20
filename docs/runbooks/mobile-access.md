# Kaviont mobile access

Kaviont Engineering is served by the existing FastAPI workload. The Progressive Web App (PWA) uses the same application origin for the user interface and the engineering API. No second frontend service or mobile-specific API is required.

## What the PWA provides

- Installable app manifest with Kaviont name, theme, launch URL and icons.
- Standalone app display when installed on a supported device.
- Touch-friendly bottom navigation on narrow screens.
- iOS installation guidance and the browser installation prompt where supported.
- Service-worker caching for the application shell: HTML, JavaScript, CSS, manifest and icons.
- Network-only handling for /v1/ APIs. Repository, security, Kubernetes and pipeline data are not placed in the offline cache.

The PWA is an online engineering client. When disconnected, the cached shell may open, but live repository, security and cluster data are unavailable.

## Local verification

On the development machine:

    cp .env.example .env
    # Set KAVIONT_GITHUB_TOKEN in .env
    make dev-up

Open:

    http://127.0.0.1:8080/engineering/

Localhost is suitable for testing on the same computer. An iPhone cannot access 127.0.0.1 on the developer machine: that address points back to the iPhone itself.

## Server deployment model

Build and deploy the same hello-api container image that serves the desktop portal. The PWA is part of that image.

For Docker Compose on a server, keep the API bound to loopback and place a TLS-enabled reverse proxy in front of it. For Kubernetes, expose the ClusterIP Service only through an ingress or gateway that terminates TLS and applies the access policy. Configure:

- A DNS name that resolves to the server or ingress.
- A valid TLS certificate and HTTPS redirect.
- The read-only GitHub token through a server-side environment variable or Kubernetes Secret.
- The existing least-privilege Kubernetes Role only when runtime visibility is required.
- A VPN/private access path or an identity-aware gateway with SSO before users can reach the portal.

Do not publish the FastAPI port directly to the public internet. The current GitHub token is a server-side shared integration credential, and the engineering API does not yet implement per-user authentication, repository authorization or user-level audit logging. A network boundary such as a company VPN is appropriate for a private pilot. For broader access, add an OIDC/SSO gateway or a first-party authentication layer, repository/role scoping and audit events before public exposure.

The PWA install requirement for remote devices is HTTPS. Keep the certificate valid and the same hostname stable so the installed app can continue to reach its server.

## Install on iPhone or iPad

1. Connect the iPhone to the company VPN or approved private access network when the server is private.
2. Open the HTTPS Kaviont URL in Safari, for example https://kaviont.example.com/engineering/.
3. Tap Share.
4. Choose Add to Home Screen.
5. Enable Open as Web App.
6. Tap Add.

Kaviont appears as an icon on the Home Screen and opens in its own app-style window. The install option is controlled by iOS and the browser, so the portal cannot force it.

## Install on Android

1. Open the HTTPS Kaviont URL in Chrome.
2. Open the browser menu.
3. Choose Install app or Add to Home screen, depending on the browser.
4. Confirm the installation.

## Operational checks

- Confirm /engineering/manifest.webmanifest returns the PWA manifest.
- Confirm /engineering/service-worker.js returns JavaScript with Service-Worker-Allowed: /engineering/.
- Confirm the server is reachable over HTTPS from the mobile network or VPN.
- Confirm /v1/engineering/status and the other API calls are protected by the same access boundary.
- Verify an offline launch shows the cached shell but does not show stale repository, vulnerability or Kubernetes data.
- After a new PWA release, reload the app once while online so the service worker can update its cached shell.

## Native application later

A native iOS/Android client is not required for the current monitoring and inspection workflow. Consider native apps only if a later requirement needs deeper device integration, managed push notifications, background work or app-store distribution. The PWA keeps one UI codebase and can be installed on supported mobile devices.
