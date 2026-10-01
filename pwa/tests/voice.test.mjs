import test from 'node:test';
import assert from 'node:assert/strict';
import {VoiceDictation,installVoice,voiceReady} from '../public/voice.mjs';
import {VOICE_FILES,VOICE_CACHE} from '../public/voice-assets.mjs';

test('cancel during microphone shutdown prevents recognition from starting',async()=>{
  let finish;let workers=0;
  globalThis.Worker=class {constructor(){workers++;}postMessage(){}terminate(){}};
  const voice=new VoiceDictation();voice.context={state:'running',close:()=>new Promise(resolve=>{finish=resolve;})};voice.parts=[new Float32Array([0.1])];voice.length=1;voice.rate=16000;
  const stopping=voice.stop();voice.cancel();finish();
  await assert.rejects(stopping,{name:'AbortError'});assert.equal(workers,0);
});

function mockGlobals(t,{cache,fetch,estimate}){
 const saved=new Map(['caches','navigator','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 Object.defineProperty(globalThis,'caches',{configurable:true,value:{open:async()=>cache}});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{storage:{estimate:estimate||(async()=>({}))}}});
 Object.defineProperty(globalThis,'fetch',{configurable:true,value:fetch});
 t.after(()=>{for(const[k,v]of saved)v?Object.defineProperty(globalThis,k,v):delete globalThis[k];});
}
test('corrupt cache is repaired and retry keeps already verified runtime file',async t=>{
 const {readFile}=await import('node:fs/promises');const file=VOICE_FILES[0];const bytes=await readFile(new URL('../public'+file.url,import.meta.url));
 const saved=new Map([[file.url,new Response('corrupt')]]);let downloads=0,removed=0;
 const cache={match:async url=>saved.get(url)?.clone(),delete:async url=>{removed++;return saved.delete(url);},put:async(url,response)=>saved.set(url,response)};
 mockGlobals(t,{cache,fetch:async url=>{if(url===file.url){downloads++;return new Response(bytes);}throw new Error('network interrupted');}});
 await assert.rejects(installVoice(),/network interrupted/);assert.equal(downloads,1);assert.equal(removed,1);
 await assert.rejects(installVoice(),/network interrupted/);assert.equal(downloads,1);assert.equal((await saved.get(file.url).clone().arrayBuffer()).byteLength,file.size);
});
test('quota rejection and cancellation never start a model download',async t=>{
 let downloads=0;const cache={match:async()=>undefined};
 mockGlobals(t,{cache,fetch:async()=>{downloads++;throw new Error('unexpected');},estimate:async()=>({quota:10,usage:9})});
 await assert.rejects(installVoice(),/Недостаточно места/);
 const controller=new AbortController();controller.abort();await assert.rejects(installVoice({signal:controller.signal}),{name:'AbortError'});assert.equal(downloads,0);
});
test('voice files require matching length and SHA256',async()=>{
 const {verifyVoiceFile}=await import('../public/voice-assets.mjs');
 const file={name:'small',size:3,sha256:'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'};
 await verifyVoiceFile(file,new TextEncoder().encode('abc'));
 await assert.rejects(verifyVoiceFile(file,new TextEncoder().encode('abd')),/контрольная сумма/);
 await assert.rejects(verifyVoiceFile(file,new TextEncoder().encode('a')),/Неполный файл/);
});
