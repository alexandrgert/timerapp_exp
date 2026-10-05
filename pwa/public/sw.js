'use strict';
const CACHE = 'tasktimer-shell-__TASKTIMER_REVISION__';
const ASSETS = ['/', '/index.html', '/app.mjs', '/model.mjs', '/desktop-domain.mjs', '/repository.mjs', '/sync-protocol.mjs', '/webdav-client.mjs', '/sync-controller.mjs', '/voice-ui.mjs', '/voice.mjs', '/voice-assets.mjs', '/voice-worker.mjs', '/voice-worklet.mjs', '/pwa.mjs', '/styles.css', '/manifest.webmanifest', '/icons/icon.svg', '/icons/icon-192.png', '/icons/icon-512.png'];
self.addEventListener('install', event => {
  // No automatic skipWaiting: an existing client explicitly accepts updates.
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS.map(url => new Request(url, {cache: 'reload'})))));
});
self.addEventListener('activate', event => {
  // Keep two prior shells for open tabs; bound storage across repeated updates.
  event.waitUntil((async () => {
    const old = (await caches.keys()).filter(name => name.startsWith('tasktimer-shell-') && name !== CACHE);
    await Promise.all(old.slice(0, Math.max(0, old.length - 2)).map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'TASKTIMER_APPLY_UPDATE') event.waitUntil(self.skipWaiting());
});
const VOICE_RUNTIME = ['/voice-assets/sherpa-onnx-asr.js','/voice-assets/sherpa-onnx-wasm-main-vad-asr.js','/voice-assets/sherpa-onnx-wasm-main-vad-asr.wasm'];
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.search || request.headers.has('authorization')) return;
  if (VOICE_RUNTIME.includes(url.pathname)) {
    event.respondWith(caches.open('tasktimer-voice-v1').then(async cache => (await cache.match(url.pathname)) || fetch(request)));
    return;
  }
  if (!ASSETS.includes(url.pathname)) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(url.pathname)) || fetch(request)));
});
