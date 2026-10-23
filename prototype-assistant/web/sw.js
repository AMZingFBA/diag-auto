// Service worker minimal : rend la page installable et l'ouvre même sans réseau.
// Réseau d'abord (le code change souvent pendant le prototype), copie locale en secours.
const CACHE = "diagauto-v10";
const FICHIERS = ["./", "index.html", "app.js", "boussole.js", "liaison.js", "style.css", "capture-son.js", "icon.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FICHIERS))));
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname === "/ws") return;
  e.respondWith(
    fetch(e.request, { cache: "no-cache" }) // jamais l'ancienne page gardée par le navigateur (test du 23/10)
      .then((reponse) => {
        const copie = reponse.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copie));
        return reponse;
      })
      .catch(() => caches.match(e.request))
  );
});
