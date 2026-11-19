/**
 * FamilyConnect AI - Progressive Web App Service Worker (Static-Only)
 * 
 * SECURITY MANDATE:
 * 1. Only static application shell assets (HTML, CSS, JS, icons, fonts) are cached.
 * 2. Authenticated API endpoints (/api/*), private incidents, and JWT credentials
 *    are NEVER cached in the service worker cache.
 * 3. Emergency SOS dispatch strictly requires active network connectivity (Wi-Fi or cellular).
 *    Offline emergency dispatch or continuous background GPS tracking is NOT fabricated.
 */

const CACHE_NAME = 'familyconnect-static-v2';

// Core application shell assets cached on install
const STATIC_SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/icons/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-192.png',
  '/icons/icon-maskable-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_SHELL_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 1. SECURITY FILTER: Never intercept non-GET requests (e.g. POST /api/emergencies/sos)
  if (request.method !== 'GET') {
    return;
  }

  // 2. SECURITY FILTER: Strictly bypass all API endpoints, auth tokens, docs, and WebSockets
  // Private health records, incidents, users, and tokens MUST NOT be stored in cache
  if (
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/docs') ||
    url.pathname.startsWith('/openapi.json') ||
    url.protocol === 'ws:' ||
    url.protocol === 'wss:' ||
    request.headers.has('Authorization')
  ) {
    return;
  }

  // 3. For navigation requests (loading index.html app shell): Network-First with cache fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => {
        return caches.match('/index.html') || caches.match('/');
      })
    );
    return;
  }

  // 4. For static bundled assets (Vite hashed bundles, images, icons, fonts): Stale-While-Revalidate
  // Strictly enforce that only static assets are stored in the cache
  const isStaticAsset = (
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.woff2') ||
    url.pathname.endsWith('.webmanifest') ||
    url.pathname === '/favicon.ico'
  );

  if (!isStaticAsset) {
    // Unknown or dynamic non-asset request: network-only without caching
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      const fetchPromise = fetch(request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
