'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const http = require('node:http');
function request(socketPath, resource, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({agent: false, socketPath, path: resource, method: options.method || 'GET'}, res => {
      const chunks = []; res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => resolve({status: res.statusCode, ok: res.statusCode === 200, headers: res.headers, text: Buffer.concat(chunks).toString()}));
    }); req.on('error', reject); req.end(options.body);
  });
}
const {mkdtemp, rm} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const path = require('node:path');
async function running(t) {
  const data = await mkdtemp(path.join(tmpdir(), 'tasktimer-http-'));
  const socketPath = path.join(data, 'http.sock');
  const shim = `const http=require('node:http');const listen=http.Server.prototype.listen;http.Server.prototype.listen=function(){return listen.call(this,process.argv[1]);};require(process.argv[2]);`;
  const child = spawn(process.execPath, ['-e', shim, socketPath, path.resolve(__dirname, '../server.cjs')], {cwd: path.resolve(__dirname, '..'), env: {...process.env, PORT: '18081', CLOUDCLI_DATA_DIR: data}, stdio: ['ignore', 'pipe', 'pipe']});
  let error = ''; child.stderr.on('data', chunk => error += chunk);
  t.after(async () => {child.kill(); await rm(data, {recursive: true, force: true});});
  const url = socketPath;
  for (let i = 0; i < 100; i++) {
    try { if ((await request(url, '/health')).ok) return url; } catch (cause) { error = String(cause) + ' ' + String(cause.cause); }
    if (child.exitCode !== null) throw Error(error);
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw Error('Server did not start: ' + error);
}
test('HTTP interface rejects writes and private paths', async t => {
  const url = await running(t);
  assert.equal((await request(url, '/', {method: 'POST', body: 'private'})).status, 405);
  for (const resource of ['/.env', '/server.js', '/package.json', '/data/state.json', '/icons/../../../package.json']) {
    assert.equal((await request(url, resource)).status, 404, resource);
  }
});
test('manifest exposes installable icons and service worker is JavaScript with restrictive headers', async t => {
  const url = await running(t);
  const manifest = await request(url, '/manifest.webmanifest');
  assert.equal(manifest.status, 200);
  assert.equal(JSON.parse(manifest.text).display, 'standalone');
  for (const icon of JSON.parse(manifest.text).icons.filter(icon => icon.type === 'image/png')) {
    const response = await request(url, icon.src);
    assert.equal(response.status, 200); assert.equal(response.headers['content-type'], 'image/png');
  }
  const response = await request(url, '/sw.js');
  assert.equal(response.status, 200);
  assert.match(response.headers['content-type'], /^text\/javascript/);
  assert.equal(response.headers['cache-control'], 'no-store');
  assert.match(response.headers['content-security-policy'], /script-src 'self'/);
  assert.doesNotMatch(response.text, /__TASKTIMER_REVISION__/);
  const notes=await request(url,'/release-notes.json');assert.equal(notes.status,200);assert.match(notes.headers['content-type'],/^application\/json/);assert.ok(response.text.includes(JSON.parse(notes.text).revision));
  const head = await request(url, '/manifest.webmanifest', {method: 'HEAD'});
  assert.equal(head.status, 200); assert.equal(head.text, '');
});
test('worker activation bounds old shell caches without removing unrelated browser caches', async () => {
  const vm = require('node:vm');
  const {readFile} = require('node:fs/promises');
  const handlers = {}; const removed = [];
  vm.runInNewContext(await readFile(path.resolve(__dirname, '../public/sw.js'), 'utf8'), {
    self: {addEventListener: (name, handler) => handlers[name] = handler, clients: {claim: async () => {}}},
    caches: {keys: async () => ['tasktimer-shell-old1', 'unrelated', 'tasktimer-shell-old2', 'tasktimer-shell-old3', 'tasktimer-shell-__TASKTIMER_REVISION__'], delete: async name => {removed.push(name);}}
  });
  let done; handlers.activate({waitUntil: promise => done = promise}); await done;
  assert.deepEqual(removed, ['tasktimer-shell-old1']);
});
