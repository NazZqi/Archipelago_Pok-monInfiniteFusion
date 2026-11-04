// Como Last Havens: solo muestra offline.html si falla la navegación. No guarda el juego, que
// ya va por bloques en OPFS, ni toca otros pedidos: las cabeceras COOP/COEP quedan intactas.
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open('offline-1').then((c) => c.add('/offline.html')).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => caches.match('/offline.html')));
});
