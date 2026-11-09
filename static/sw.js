/* Safe Circles service worker: cache the app shell and any toolkit page a
   facilitator opens, so the toolkit works offline in a venue with no signal.
   Personal pages (/me, /admin, /lead/*) are never cached. */
const VERSION = 'sc-v1';
const SHELL = ['/', '/toolkit', '/toolkit/referrals', '/guidelines', '/static/style.css', '/static/app.js', '/static/icons/icon.svg'];
const CACHEABLE = /^\/(toolkit(\/[a-z0-9-]+)?|guidelines|about|static\/.*)?$/;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || !CACHEABLE.test(url.pathname)) return;
  e.respondWith(
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(VERSION).then((c) => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match('/toolkit')))
  );
});
