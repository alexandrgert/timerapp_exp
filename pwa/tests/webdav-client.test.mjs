import test from 'node:test';
import assert from 'node:assert/strict';
import { createWebDavClient, resolveWebDavUrls } from '../public/webdav-client.mjs';

test('HTTPS read uses bounded direct CORS request and exposes strong ETag', async () => {
  let request;
  const client = createWebDavClient({ url: 'https://dav.example/tasks.json', username: 'user', password: 'pass', fetchImpl: async (...args) => {
    request = args;
    return new Response('{"version":2}', { headers: { ETag: '"revision-1"' } });
  } });
  assert.deepEqual(await client.read(), { body: '{"version":2}', etag: '"revision-1"' });
  assert.equal(request[1].mode, 'cors');
  assert.equal(request[1].credentials, 'omit');
  assert.equal(request[1].redirect, 'error');
  assert.equal(request[1].cache, 'no-store');
  assert.equal(request[1].headers.Authorization, 'Basic dXNlcjpwYXNz');
});

test('PUT requires exact revision or explicit create and reports 412', async () => {
  const calls = [];
  const client = createWebDavClient({ url: 'https://dav.example/tasks.json.v2.json', fetchImpl: async (_, options) => {
    calls.push(options); return new Response(null, { status: calls.length === 2 ? 412 : 204 });
  } });
  await assert.rejects(client.write('{}'), { code: 'ETAG' });
  await client.write('{}', { create: true });
  assert.equal(calls[0].headers['If-None-Match'], '*');
  await assert.rejects(client.write('{}', { etag: '"a"' }), { code: 412, status: 412 });
  assert.equal(calls[1].headers['If-Match'], '"a"');
  assert.equal(calls[1].headers['Content-Type'], 'application/json; charset=utf-8');
});

test('refuses unsafe endpoints, weak ETag, missing ETag and handles 404', async () => {
  for (const url of ['http://dav.example/a', 'https://user:pass@dav.example/a', 'https://dav.example/a#b']) {
    assert.throws(() => createWebDavClient({ url }), { code: 'URL' });
  }
  for (const etag of [null, 'W/"a"', '*']) {
    const client = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => new Response('{}', { headers: etag ? { ETag: etag } : {} }) });
    await assert.rejects(client.read(), { code: 'ETAG' });
    await assert.rejects(client.write('{}', { etag }), { code: 'ETAG' });
  }
  const client = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => new Response(null, { status: 404 }) });
  assert.equal(await client.read(), null);
});

test('limits declared and streamed bytes and rejects invalid UTF-8', async () => {
  for (const response of [
    new Response('{}', { headers: { ETag: '"a"', 'Content-Length': '33554433' } }),
    new Response(new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(33554433)); controller.close(); } }), { headers: { ETag: '"a"' } }),
  ]) {
    const client = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => response });
    await assert.rejects(client.read(), { code: 'SIZE' });
  }
  const client = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => new Response(new Uint8Array([255]), { headers: { ETag: '"a"' } }) });
  await assert.rejects(client.read(), { code: 'BODY' });
});

test('network errors explain CORS without reflecting secret-bearing errors; cancellation preserved', async () => {
  const client = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => { throw new Error('private-value'); } });
  await assert.rejects(client.read(), error => error.code === 'NETWORK_CORS' && error.message.includes('Access-Control-Expose-Headers') && !error.message.includes('private-value'));
  const aborted = new DOMException('Aborted', 'AbortError');
  const cancelClient = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => { throw aborted; } });
  await assert.rejects(cancelClient.read(), error => error === aborted);
  const redirected = createWebDavClient({ url: 'https://dav.example/a', fetchImpl: async () => ({ redirected: true }) });
  await assert.rejects(redirected.read(), { code: 'REDIRECT' });
});

test('legacy migration read does not demand ETag while v2 read still does',async()=>{
 const client=createWebDavClient({url:'https://dav.example/tasks.json',fetchImpl:async()=>new Response('{"tasks":[]}')});
 assert.deepEqual(await client.readLegacy(),{body:'{"tasks":[]}',etag:null});
 await assert.rejects(client.read(),{code:'ETAG'});
});


test('server and path resolve to the same original and v2 resources as full URL',()=>{
 const expected={legacyUrl:'https://webdav.cloudbeeline.ru/tasktimer/data.json',url:'https://webdav.cloudbeeline.ru/tasktimer/data.json.v2.json'};
 for(const server of ['https://webdav.cloudbeeline.ru','https://webdav.cloudbeeline.ru/'])assert.deepEqual(resolveWebDavUrls(server,'tasktimer/data.json'),expected);
 assert.deepEqual(resolveWebDavUrls(expected.legacyUrl),expected);
 assert.deepEqual(resolveWebDavUrls('https://webdav.cloudbeeline.ru','/tasktimer/data.json'),expected);
 assert.equal(resolveWebDavUrls('https://dav.example/dav/user','folder/data.json').legacyUrl,'https://dav.example/dav/user/folder/data.json');
 assert.equal(resolveWebDavUrls('https://dav.example','мои задачи/data.json').legacyUrl,new URL('https://dav.example/мои задачи/data.json').href);
});
test('invalid, ambiguous and service file addresses fail before network access',()=>{
 for(const [server,path] of [
 ['https://webdav.cloudbeeline.ru',''],['https://cloudbeeline.ru/drive/123','tasktimer/data.json'],
 ['https://dav.example/data.json','tasktimer/data.json'],['http://dav.example','data.json'],
 ['https://user:private@dav.example/data.json',''],['https://dav.example/data.json?token=private',''],
 ['https://dav.example/data.json.v2.json',''],['https://dav.example/data.sync-meta.json',''],
 ...['../data.json','%2e%2e/data.json','folder/%2fdata.json','folder//data.json','data.json#part','https://other.example/data.json','//other.example/data.json','%zz/data.json'].map(path=>['https://dav.example',path])
 ])assert.throws(()=>resolveWebDavUrls(server,path),error=>error.code==='URL'&&!error.message.includes('private'));
});
