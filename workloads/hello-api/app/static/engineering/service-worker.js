"use strict";

const CACHE_PREFIX = "kaviont-engineering-shell-";
const CACHE_NAME = CACHE_PREFIX + "v1";
const APP_SHELL = [
  "/engineering",
  "/engineering/manifest.webmanifest",
  "/engineering/assets/engineering.css",
  "/engineering/assets/engineering.js",
  "/engineering/assets/icon-192.png",
  "/engineering/assets/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Repository, security, Kubernetes and other API responses are network-only.
  if (url.pathname.startsWith("/v1/") || request.headers.has("authorization")) {
    event.respondWith(fetch(request));
    return;
  }

  const isAppNavigation =
    request.mode === "navigate" &&
    (url.pathname === "/engineering" || url.pathname === "/engineering/");

  if (isAppNavigation) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put("/engineering", copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match("/engineering");
          if (cached) return cached;
          return new Response(
            "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Kaviont offline</title><body style=\"font:16px system-ui;background:#0a0f15;color:#eef4f9;padding:2rem\"><h1>Kaviont is offline</h1><p>Reconnect to your Kaviont server to load live engineering data.</p></body></html>",
            { headers: { "Content-Type": "text/html; charset=utf-8" }, status: 503 }
          );
        })
    );
    return;
  }

  const isStaticAsset =
    url.pathname.startsWith("/engineering/assets/") ||
    url.pathname === "/engineering/manifest.webmanifest";

  if (isStaticAsset) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const update = fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        });
        return cached || update;
      })
    );
  }
});
