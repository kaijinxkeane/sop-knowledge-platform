// SOP Assistant service worker: makes the app installable and shows a
// friendly page when the server can't be reached.
//
// It never caches SOPs, answers or any /api response: only the offline page
// and its style and icon are stored, so nothing readable stays on a device.
const CACHE = "sop-offline-v1";
const OFFLINE = ["/offline.html", "/offline.css", "/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(OFFLINE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (req.mode === "navigate") {
    // Always the network; the offline page only when it fails.
    event.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
    return;
  }
  if (OFFLINE.includes(url.pathname)) {
    event.respondWith(fetch(req).catch(() => caches.match(url.pathname)));
  }
});
