/* ============================================================
   Kitchen.exe — Service Worker
   Estrategia:
   - App shell (HTML, manifest, iconos): cache-first
   - Feeds RSS y APIs externas: network-first con fallback a cache
   - Nada de cachear POST ni navegaciones externas
   ============================================================ */

const VERSION = 'kitchen-exe-v1.0.0';
const SHELL_CACHE = `${VERSION}-shell`;
const RUNTIME_CACHE = `${VERSION}-runtime`;

// Archivos que forman el "app shell" (se cachean al instalar)
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png'
];

/* ---------- INSTALL ---------- */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => {
      // addAll falla entero si un archivo no existe; usamos add individual tolerante
      return Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn('[SW] No se pudo cachear:', url, err);
          })
        )
      );
    }).then(() => self.skipWaiting())
  );
});

/* ---------- ACTIVATE ---------- */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith('kitchen-exe-') && !key.startsWith(VERSION))
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

/* ---------- FETCH ---------- */
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Solo GET
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Ignorar extensiones de navegador
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

  // Mismo origen → cache-first (app shell)
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Fuentes externas (feeds RSS, TheMealDB, Reddit, imágenes) → network-first
  event.respondWith(networkFirst(req));
});

/* ---------- ESTRATEGIAS ---------- */
async function cacheFirst(req) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(req, { ignoreSearch: true });
  if (cached) return cached;

  try {
    const res = await fetch(req);
    if (res && res.status === 200 && res.type === 'basic') {
      cache.put(req, res.clone());
    }
    return res;
  } catch (err) {
    // Fallback al index.html si es navegación
    if (req.mode === 'navigate') {
      const fallback = await cache.match('./index.html');
      if (fallback) return fallback;
    }
    throw err;
  }
}

async function networkFirst(req) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const res = await fetch(req);
    // Cachear solo respuestas válidas y "simples" (evita opaque por CORS)
    if (res && res.status === 200 && res.type !== 'opaque') {
      // Limitar tamaño del runtime cache
      const keys = await cache.keys();
      if (keys.length > 80) {
        await cache.delete(keys[0]);
      }
      cache.put(req, res.clone());
    }
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw err;
  }
}

/* ---------- MENSAJES DESDE LA APP ---------- */
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data === 'CLEAR_CACHE') {
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => caches.delete(k)))
    ).then(() => {
      event.source?.postMessage({ type: 'CACHE_CLEARED' });
    });
  }
});