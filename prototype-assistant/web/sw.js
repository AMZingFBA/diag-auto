// Service worker minimal : rend la page installable et l'ouvre même sans réseau.
// Réseau d'abord (le code change souvent pendant le prototype), copie locale en secours.
const CACHE = "diagauto-v19";
const FICHIERS = ["./", "index.html", "app.js", "boussole.js", "liaison.js", "style.css", "capture-son.js", "icon.svg", "manifest.webmanifest"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FICHIERS))));
// Les anciennes copies sont effacées : hors réseau, c'est la dernière version qui s'ouvre, pas la plus ancienne.
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((noms) => Promise.all(noms.filter((n) => n !== CACHE).map((n) => caches.delete(n)))).then(() => self.clients.claim())));
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
      .catch(() => caches.open(CACHE).then((c) => c.match(e.request)))
  );
});
