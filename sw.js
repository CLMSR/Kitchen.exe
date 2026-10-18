/* Kitchen.exe PWA service worker — versioned shell cache, conservative network handling. */
const VERSION = 'kitchen-exe-v2.5.0';
const SHELL_CACHE = `${VERSION}-shell`;
const SHELL_ASSETS = [
  './', './index.html', './manifest.json', './recipe-core.js', './storage-core.js',
  './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png', './icons/favicon-32.png', './icons/favicon-16.png', './icons/kitchen-logo.svg', './icons/recipe-placeholder.svg'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await Promise.all(SHELL_ASSETS.map(async asset => {
      try { await cache.add(asset); } catch (error) { console.warn('[SW] Optional shell asset failed:', asset, error); }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('kitchen-exe-') && key !== SHELL_CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // Do not cache feeds, APIs, proxies or external content.

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(SHELL_CACHE);
          cache.put('./index.html', response.clone());
        }
        return response;
      } catch {
        const cache = await caches.open(SHELL_CACHE);
        return (await cache.match('./index.html')) || Response.error();
      }
    })());
    return;
  }

  const isShellAsset = /\.(html|js|css|json|png|svg|webmanifest)(\?.*)?$/i.test(url.pathname) || url.pathname.endsWith('/');
  if (!isShellAsset) return;
  event.respondWith((async () => {
    const cache = await caches.open(SHELL_CACHE);
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok && response.type === 'basic') cache.put(request, response.clone());
    return response;
  })());
});

self.addEventListener('message', event => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
  if (event.data === 'CLEAR_CACHE') {
    event.waitUntil(caches.keys().then(keys => Promise.all(keys.map(key => caches.delete(key)))).then(() => {
      event.source?.postMessage({ type: 'CACHE_CLEARED' });
    }));
  }
});
