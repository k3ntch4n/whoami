// Offline cache: always try the network, fall back to the saved copy.
const CACHE = "rebonds-v7";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  // network first so updates show up at once; cache when offline
  e.respondWith(caches.open(CACHE).then((c) =>
    fetch(e.request).then((res) => {
      if (res && (res.ok || res.type === "opaque")) c.put(e.request, res.clone());
      return res;
    }).catch(() => c.match(e.request))
  ));
});
