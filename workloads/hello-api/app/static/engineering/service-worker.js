const CACHE_NAME = "kaviont-engineering-shell-v1";
const SHELL_URLS = [
  "/engineering/",
  "/engineering/manifest.webmanifest",
  "/engineering/assets/engineering.css",
  "/engineering/assets/engineering.js",
  "/engineering/assets/kaviont-icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key.startsWith("kaviont-engineering-") && key !== CACHE_NAME)
        .map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // Never cache live repository, security, market or Kubernetes API responses.
  if (url.pathname.startsWith("/v1/") || request.headers.has("authorization")) return;

  if (request.mode === "navigate" && url.pathname.startsWith("/engineering/")) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/engineering/", copy));
        }
        return response;
      }).catch(async () => {
        const cached = await caches.match("/engineering/");
        if (cached) return cached;
        return new Response("Kaviont is offline. Reconnect to refresh live engineering data.", {
          status: 503,
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        });
      })
    );
    return;
  }

  if (SHELL_URLS.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }))
    );
  }
});
