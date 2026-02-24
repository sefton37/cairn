/**
 * Talking Rock PWA Service Worker
 *
 * Strategy:
 * - App shell (HTML, JS, CSS, manifest, icons): cache-first with version-based invalidation
 * - API routes (/rpc, /auth, /rpc/events): network-only — never cache auth or live data
 */

const CACHE_VERSION = 'tr-shell-v3';

// Files that form the app shell — everything needed to render offline
const APP_SHELL = [
  '/app/',
  '/app/index.html',
  '/app/app.js',
  '/app/app.css',
  '/app/manifest.json',
  '/app/icons/icon-192.svg',
  '/app/icons/icon-512.svg',
];

// URL prefixes that must always go to the network
const NETWORK_ONLY_PREFIXES = ['/rpc', '/auth'];

// ── Install ──────────────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => {
      // Cache what we can; don't let a missing icon block installation
      return Promise.allSettled(
        APP_SHELL.map((url) =>
          cache.add(url).catch((err) => {
            console.warn(`[SW] Failed to cache ${url}:`, err.message);
          })
        )
      );
    }).then(() => {
      // Activate immediately without waiting for existing tabs to close
      return self.skipWaiting();
    })
  );
});

// ── Activate ─────────────────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_VERSION)
          .map((key) => {
            console.log(`[SW] Deleting old cache: ${key}`);
            return caches.delete(key);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  // API routes are always network-only
  if (NETWORK_ONLY_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    event.respondWith(fetch(event.request));
    return;
  }

  // App shell: cache-first, falling back to network, then offline page
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;

      return fetch(event.request).then((response) => {
        // Only cache successful GET responses for app-shell assets
        if (
          event.request.method === 'GET' &&
          response.ok &&
          url.pathname.startsWith('/app/')
        ) {
          const responseClone = response.clone();
          caches.open(CACHE_VERSION).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      }).catch(() => {
        // Offline fallback: serve index.html for navigation requests
        if (event.request.mode === 'navigate') {
          return caches.match('/app/index.html');
        }
        // For other resources, let the error propagate naturally
        return new Response('Offline', { status: 503 });
      });
    })
  );
});
