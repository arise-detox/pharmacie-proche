/* Service worker : l'appli s'ouvre sans réseau, les zones déjà consultées restent disponibles.
   - fichiers du site : réseau d'abord (mises à jour immédiates), cache en secours
   - tuiles de données : cache d'abord, rafraîchies en arrière-plan */
var SHELL = "pharma-shell-v1", DATA = "pharma-data-v1", MAX_TILES = 160;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(SHELL).then(function (c) {
    return c.addAll(["./", "./index.html", "./manifest.webmanifest", "./icon.svg"]);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== SHELL && k !== DATA; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trim(cache) {
  return cache.keys().then(function (ks) {
    var extra = ks.length - MAX_TILES, jobs = [];
    for (var i = 0; i < extra; i++) jobs.push(cache.delete(ks[i]));
    return Promise.all(jobs);
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.indexOf("/data/p/") !== -1) {
    e.respondWith(caches.open(DATA).then(function (c) {
      return c.match(req).then(function (hit) {
        var net = fetch(req).then(function (res) {
          if (res.ok) { c.put(req, res.clone()).then(function () { return trim(c); }); }
          return res;
        }).catch(function () { return null; });
        if (hit) { e.waitUntil(net); return hit; }
        return net.then(function (res) { return res || new Response("[]", { status: 503, headers: { "Content-Type": "application/json" } }); });
      });
    }));
    return;
  }

  e.respondWith(
    fetch(req, { cache: "no-cache" }).then(function (res) {
      if (res.ok) { var copy = res.clone(); caches.open(SHELL).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (r) {
        if (r) return r;
        if (req.mode === "navigate") return caches.match("./index.html");
        return new Response("", { status: 504 });
      });
    })
  );
});
