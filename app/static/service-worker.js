// Keep the worker for installation, but never intercept pages, forms, payments,
// or the main stylesheet. Authenticated content and app.css must stay network-first.
const CACHE_NAME = "umshado-static-v3";
const STATIC_ASSETS = new Set([
  "/static/images/umshado-logo.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png"
]);

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith("umshado-static-") && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.mode === "navigate") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !STATIC_ASSETS.has(url.pathname)) return;

  event.respondWith((async () => {
    try {
      const response = await fetch(request);
      if (response.ok) {
        event.waitUntil(caches.open(CACHE_NAME)
          .then((cache) => cache.put(request, response.clone()))
          .catch(() => {}));
      }
      return response;
    } catch (error) {
      const cached = await caches.match(request);
      if (cached) return cached;
      throw error;
    }
  })());
});
