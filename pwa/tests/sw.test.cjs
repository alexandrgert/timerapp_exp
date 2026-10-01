'use strict';
// Handler-contract tests in a VM. These do not prove real-browser offline support.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const source = readFileSync(path.join(__dirname, '../public/sw.js'), 'utf8');
const origin = 'https://tasktimer.test';
function worker({installationError, offline = false, cacheEntries = {}, cacheNames = []} = {}) {
  const handlers = {}, calls = {skipWaiting: 0, claim: 0, fetched: [], precached: [], deleted: []};
  vm.runInNewContext(source, {
    URL,
    Request: class extends Request {constructor(url, options) {super(new URL(url, origin), options);}},
    self: {location: {origin}, addEventListener: (name, handler) => handlers[name] = handler,
      skipWaiting: async () => {calls.skipWaiting++;}, clients: {claim: async () => {calls.claim++;}}},
    caches: {
      open: async () => ({addAll: async requests => {
        calls.precached.push(...requests); if (installationError) throw installationError;
      }, match: async resource => cacheEntries[resource]}),
      keys: async () => cacheNames,
      delete: async name => {calls.deleted.push(name); return true;}
    },
    fetch: async request => {
      calls.fetched.push(request.url);
      if (offline) throw new TypeError('network unavailable');
      return new Response('network asset');
    }
  });
  const lifecycle = (name, data) => {
    let pending;
    handlers[name]({data, waitUntil: promise => {pending = promise;}});
    return pending;
  };
  const fetchEvent = (url, options) => {
    let pending;
    handlers.fetch({request: new Request(new URL(url, origin), options), respondWith: promise => {pending = promise;}});
    return pending;
  };
  return {calls, lifecycle, fetchEvent};
}
test('installation precaches complete shell and waits for user activation', async () => {
  const sw = worker(); await sw.lifecycle('install');
  assert.deepEqual(sw.calls.precached.map(request => new URL(request.url).pathname), [
    '/', '/index.html', '/app.mjs', '/model.mjs', '/repository.mjs', '/sync-protocol.mjs', '/webdav-client.mjs', '/sync-controller.mjs', '/voice-ui.mjs', '/voice.mjs', '/voice-assets.mjs', '/voice-worker.mjs', '/voice-worklet.mjs', '/pwa.mjs', '/styles.css',
    '/manifest.webmanifest', '/icons/icon.svg', '/icons/icon-192.png', '/icons/icon-512.png'
  ]);
  assert.ok(sw.calls.precached.every(request => request.cache === 'reload'));
  assert.equal(sw.calls.skipWaiting, 0); assert.equal(sw.calls.claim, 0);
});
test('failed precache rejects installation without forcing activation', async () => {
  const error = new Error('storage quota exceeded');
  const sw = worker({installationError: error});
  await assert.rejects(sw.lifecycle('install'), /storage quota exceeded/);
  assert.equal(sw.calls.skipWaiting, 0); assert.equal(sw.calls.claim, 0);
});
test('offline shell uses cache; missing asset rejects instead of successful placeholder', async () => {
  const sw = worker({offline: true, cacheEntries: {'/': new Response('saved shell')}});
  assert.equal(await (await sw.fetchEvent('/')).text(), 'saved shell');
  assert.deepEqual(sw.calls.fetched, []);
  await assert.rejects(sw.fetchEvent('/app.mjs'), /network unavailable/);
  assert.deepEqual(sw.calls.fetched, [origin + '/app.mjs']);
});
test('online cache miss fetches static asset while cached modules keep matching shell', async () => {
  const sw = worker({cacheEntries: {'/model.mjs': new Response('saved module')}});
  assert.equal(await (await sw.fetchEvent('/model.mjs')).text(), 'saved module');
  assert.equal(await (await sw.fetchEvent('/app.mjs')).text(), 'network asset');
  assert.deepEqual(sw.calls.fetched, [origin + '/app.mjs']);
});
test('worker never intercepts external, authorized, query, nonstatic or write requests', () => {
  const sw = worker();
  for (const [url, options] of [
    ['https://webdav.example/state.json'], ['/app.mjs?token=example'], ['/app.mjs', {headers: {Authorization: 'test'}}],
    ['/health'], ['/state.json'], ['/app.mjs', {method: 'POST', body: 'data'}]
  ]) assert.equal(sw.fetchEvent(url, options), undefined, url);
  assert.deepEqual(sw.calls.fetched, []);
});
test('only explicit update message activates worker; activation retains two old shells', async () => {
  const sw = worker({cacheNames: ['tasktimer-shell-first', 'unrelated', 'tasktimer-shell-second', 'tasktimer-shell-third', 'tasktimer-shell-__TASKTIMER_REVISION__']});
  assert.equal(sw.lifecycle('message', {type: 'OTHER'}), undefined); assert.equal(sw.calls.skipWaiting, 0);
  await sw.lifecycle('message', {type: 'TASKTIMER_APPLY_UPDATE'}); assert.equal(sw.calls.skipWaiting, 1);
  await sw.lifecycle('activate'); assert.equal(sw.calls.claim, 1);
  assert.deepEqual(sw.calls.deleted, ['tasktimer-shell-first']);
});

test('verified voice runtime cache is available offline without precaching the model',async()=>{
 const sw=worker({offline:true,cacheEntries:{'/voice-assets/sherpa-onnx-asr.js':new Response('verified runtime')}});
 assert.equal(await(await sw.fetchEvent('/voice-assets/sherpa-onnx-asr.js')).text(),'verified runtime');
 await sw.lifecycle('install');assert.ok(sw.calls.precached.every(r=>!new URL(r.url).pathname.startsWith('/voice-assets/')));
 assert.equal(sw.fetchEvent('/voice-assets/unlisted.js'),undefined);
});
