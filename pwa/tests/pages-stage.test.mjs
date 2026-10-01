import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {renderAsset} from '../scripts/pages-stage.mjs';
const options={basePath:'/timerapp_exp/',revision:'0123456789abcdef0123456789abcdef01234567'};
const source=name=>readFile(new URL('../public/'+name,import.meta.url));
test('Pages HTML uses repository base and retains Node-root source untouched',async()=>{
 const original=await source('index.html');
 const output=renderAsset('index.html',original,options).toString();
 assert.match(output,/src="\/timerapp_exp\/app\.mjs"/);
 assert.match(output,/href="\/timerapp_exp\/manifest\.webmanifest"/);
 assert.match(output,/href="\/timerapp_exp\/"/);
 assert.match(output,/http-equiv="Content-Security-Policy"/);
 assert.match(original.toString(),/src="\/app\.mjs"/);
});
test('Pages manifest and shell worker scope both stay within repository',async()=>{
 const manifest=JSON.parse(renderAsset('manifest.webmanifest',await source('manifest.webmanifest'),options));
 assert.equal(manifest.id,'/timerapp_exp/');assert.equal(manifest.start_url,'/timerapp_exp/');assert.equal(manifest.scope,'/timerapp_exp/');
 assert.ok(manifest.icons.every(icon=>icon.src.startsWith('/timerapp_exp/icons/')));
 const sw=renderAsset('sw.js',await source('sw.js'),options).toString();
 const context={self:{addEventListener(){}},URL};vm.createContext(context);
 vm.runInContext(sw+'\nthis.exposed={CACHE,ASSETS,VOICE_RUNTIME};',context);
 assert.ok(context.exposed.ASSETS.every(url=>url.startsWith('/timerapp_exp/')));
 assert.ok(context.exposed.VOICE_RUNTIME.every(url=>url.startsWith('/timerapp_exp/voice-assets/')));
 assert.match(context.exposed.CACHE,/tasktimer-shell-pages-/);assert.ok(context.exposed.CACHE.endsWith(options.revision));
 assert.doesNotMatch(sw,/__TASKTIMER_REVISION__/);
 assert.match(sw,/startsWith\('tasktimer-shell-pages-/);
 const registration=renderAsset('pwa.mjs',await source('pwa.mjs'),options).toString();
 assert.match(registration,/register\('\/timerapp_exp\/sw\.js', \{scope: '\/timerapp_exp\/'/);
});
test('Pages voice paths and cache match SW while native model paths and vendor hashes remain untouched',async()=>{
 const assets=renderAsset('voice-assets.mjs',await source('voice-assets.mjs'),options).toString();
 const sw=renderAsset('sw.js',await source('sw.js'),options).toString();
 const cache=assets.match(/VOICE_CACHE = '([^']+)'/)[1];assert.ok(cache.startsWith('tasktimer-voice-v1-pages-'));assert.ok(sw.includes(`caches.open('${cache}')`));
 assert.equal((assets.match(/url:'\/timerapp_exp\/voice-assets\//g)||[]).length,3);
 assert.ok(assets.includes('https://huggingface.co/'));
 const voice=renderAsset('voice.mjs',await source('voice.mjs'),options).toString();
 assert.ok(voice.includes("addModule('/timerapp_exp/voice-worklet.mjs')"));assert.ok(voice.includes("new Worker('/timerapp_exp/voice-worker.mjs')"));
 assert.ok(voice.includes('tasktimer-voice-install-pages-'));
 const worker=renderAsset('voice-worker.mjs',await source('voice-worker.mjs'),options).toString();
 assert.ok(worker.includes("importScripts('/timerapp_exp/voice-assets/"));assert.ok(worker.includes("encoder:'/ru-encoder.int8.onnx'"));
 for(const name of ['sherpa-onnx-asr.js','sherpa-onnx-wasm-main-vad-asr.js','sherpa-onnx-wasm-main-vad-asr.wasm']) {
  const bytes=await source('voice-assets/'+name);assert.strictEqual(renderAsset('voice-assets/'+name,bytes,options),bytes);
 }
 const repo=renderAsset('repository.mjs',await source('repository.mjs'),options).toString();assert.ok(repo.includes("name='tasktimer-pwa-pages-"));
});
