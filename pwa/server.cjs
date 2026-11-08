'use strict';
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const {createHash} = require('node:crypto');
const port = Number.parseInt(process.env.PORT || '', 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be a valid TCP port');
if (!process.env.CLOUDCLI_DATA_DIR) throw new Error('CLOUDCLI_DATA_DIR is required');
// This runtime stores no application data. Browser data remains in IndexedDB.
const root = path.join(__dirname, 'public');
const assets = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ...['app.mjs', 'model.mjs','desktop-domain.mjs', 'repository.mjs', 'pwa.mjs', 'sw.js', 'sync-protocol.mjs', 'webdav-client.mjs','github-client.mjs','auto-sync.mjs', 'sync-controller.mjs', 'voice-ui.mjs', 'voice.mjs', 'voice-assets.mjs', 'voice-worker.mjs', 'voice-worklet.mjs'].map(name => ['/' + name, [name, 'text/javascript; charset=utf-8']]),
  ...['sherpa-onnx-asr.js','sherpa-onnx-wasm-main-vad-asr.js','sherpa-onnx-wasm-main-vad-asr.wasm'].map(name=>['/voice-assets/'+name,['voice-assets/'+name,name.endsWith('.wasm')?'application/wasm':'text/javascript; charset=utf-8']]),
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/release-notes.json', ['release-notes.json', 'application/json; charset=utf-8']],
  ['/manifest.webmanifest', ['manifest.webmanifest', 'application/manifest+json; charset=utf-8']],
  ['/icons/icon.svg', ['icons/icon.svg', 'image/svg+xml']],
  ...[192, 512].map(size => [`/icons/icon-${size}.png`, [`icons/icon-${size}.png`, 'image/png']])
]);
const guideHeaders={'content-type':'text/html; charset=utf-8','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"};
const headers = {
  'cache-control': 'no-cache',
  'content-security-policy': "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' blob:; connect-src 'self' https:; worker-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  'referrer-policy': 'no-referrer', 'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY'
};
async function main(){
 const selfhost=process.env.TASKTIMER_SELFHOST==='1';
 const api=selfhost?await require('./selfhost/api.cjs').createApi({root:process.env.CLOUDCLI_DATA_DIR,origin:process.env.TASKTIMER_PUBLIC_ORIGIN}):null;
 const render=selfhost?require('./selfhost/frontend.cjs').render:async(_name,body)=>body;
 const server=http.createServer(async (request, response) => {
  if(api&&request.url.startsWith('/api/'))return api.handle(request,response);
  request.resume();
  const reply = (status, body, extra = {}) => {
    response.writeHead(status, {...headers, 'content-type': 'text/plain; charset=utf-8', ...extra});
    response.end(request.method === 'HEAD' ? undefined : body);
  };
  if (!['GET', 'HEAD'].includes(request.method)) return reply(405, 'method not allowed\n', {allow: 'GET, HEAD'});
  let pathname;
  try {pathname = new URL(request.url, 'http://localhost').pathname;} catch {return reply(400, 'bad request\n');}
  if (pathname === '/health') return reply(200, 'ok\n', {'cache-control': 'no-store'});
  if(selfhost&&pathname==='/server-guide/'){try{return reply(200,await fs.readFile(path.join(__dirname,'selfhost/guide.html')),guideHeaders);}catch{return reply(503,'Server guide unavailable');}}
  if(pathname==='/guide/'){try{const guide=await fs.readFile(path.resolve(__dirname,'../docs/user-guide/TaskTimer-instruction.html'));return reply(200,guide,selfhost?guideHeaders:{'content-type':'text/html; charset=utf-8'});}catch{return reply(503,'Guide is temporarily unavailable\n');}}
  const asset = assets.get(pathname);
  if (!asset) return reply(404, 'not found\n', {'cache-control': 'no-store'});
  try {
    let body = await render(asset[0],await fs.readFile(path.join(root, asset[0])));
    if (pathname === '/sw.js' || pathname === '/release-notes.json') {
      // Any source edit creates a distinct worker/cache without a build step.
      const hash = createHash('sha256');
      for (const name of new Set([...assets.values()].map(value => value[0]))) {
        hash.update(name);try{hash.update(await render(name,await fs.readFile(path.join(root, name))));}catch(error){if(name!=='release-notes.json'||error.code!=='ENOENT')throw error;hash.update('optional-notes-missing');}
      }
      if(selfhost){for(const f of ['frontend.cjs','client.mjs'])hash.update(await fs.readFile(path.join(__dirname,'selfhost',f)));}
      const revision=hash.digest('hex').slice(0,24);
      body = Buffer.from(pathname==='/sw.js'?body.toString().replaceAll('__TASKTIMER_REVISION__',revision):JSON.stringify({...JSON.parse(body),revision}));
    }
    reply(200, body, {'content-type': asset[1], 'content-length': body.length, ...(pathname === '/sw.js' ? {'service-worker-allowed': '/', 'cache-control': 'no-store'} : {})});
  } catch {
    // Missing or invalid deployment must fail, never return an old successful body.
    reply(503, 'Application files are temporarily unavailable\n', {'cache-control': 'no-store'});
  }
});
 server.requestTimeout=30000;server.headersTimeout=10000;server.maxConnections=64;
 server.listen(port,'0.0.0.0');
}
main().catch(error=>{console.error('Server startup failed:',error.message);process.exitCode=1;});
