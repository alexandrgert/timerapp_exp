import {VOICE_CACHE,VOICE_FILES,VOICE_BYTES,verifyVoiceFile} from './voice-assets.mjs';
export {VOICE_BYTES};
export async function voiceReady() {
  if(!globalThis.caches) return false;
  const cache=await caches.open(VOICE_CACHE);
  return (await Promise.all(VOICE_FILES.map(file=>cache.match(file.url)))).every(Boolean);
}
export async function installVoice({signal,onProgress=()=>{}}={}) {
  const operation=async()=>{
    const cache=await caches.open(VOICE_CACHE); let loaded=0;
    for(const file of VOICE_FILES) {
      signal?.throwIfAborted();
      const cached=await cache.match(file.url);
      if(cached) {try {await verifyVoiceFile(file,await cached.arrayBuffer());loaded+=file.size;onProgress({loaded,total:VOICE_BYTES,file:file.name});continue;}catch {await cache.delete(file.url);}}
      const estimate=await navigator.storage?.estimate?.();
      if(estimate?.quota && estimate.quota-estimate.usage < file.size*2) throw new Error('Недостаточно места для голосовой модели. Освободите место и повторите.');
      const response=await fetch(file.url,{signal,credentials:'omit',cache:'no-store'});
      if(!response.ok || !response.body) throw new Error(`Не удалось загрузить ${file.name}: HTTP ${response.status}`);
      const reader=response.body.getReader(),bytes=new Uint8Array(file.size);let offset=0;
      try {while(true) {signal?.throwIfAborted();const {value,done}=await reader.read();if(done)break;if(offset+value.length>bytes.length)throw new Error('Размер модели не совпадает с ожидаемым');bytes.set(value,offset);offset+=value.length;onProgress({loaded:loaded+offset,total:VOICE_BYTES,file:file.name});}}
      finally {await reader.cancel();reader.releaseLock();}
      await verifyVoiceFile(file,bytes.subarray(0,offset));signal?.throwIfAborted();
      await cache.put(file.url,new Response(bytes,{headers:{'Content-Type':file.name.endsWith('.js')?'text/javascript':file.name.endsWith('.wasm')?'application/wasm':'application/octet-stream'}}));
      loaded+=file.size;
    }
    signal?.throwIfAborted();return true;
  };
  return navigator.locks ? navigator.locks.request('tasktimer-voice-install',{signal},operation) : operation();
}
export async function removeVoice() {
  const remove=()=>caches.delete(VOICE_CACHE);
  return navigator.locks ? navigator.locks.request('tasktimer-voice-install',remove) : remove();
}
export class VoiceDictation {
  constructor(){this.generation=0;this.parts=[];this.length=0;}
  async start({onAutoStop=()=>{},onError=()=>{}}={}) {
    if(this.context || this.worker)throw new Error('Диктовка уже выполняется');
    const generation=++this.generation;
    if(!await voiceReady())throw new Error('Сначала загрузите офлайн-модель');
    if(generation!==this.generation)throw new DOMException('Отменено','AbortError');
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true},video:false});
    if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());throw new DOMException('Отменено','AbortError');}
    this.stream=stream;this.parts=[];this.length=0;
    try {
      this.context=new AudioContext({sampleRate:16000});this.rate=this.context.sampleRate;
      await this.context.audioWorklet.addModule('/voice-worklet.mjs');
      if(generation!==this.generation)throw new DOMException('Отменено','AbortError');
      this.source=this.context.createMediaStreamSource(stream);
      this.node=new AudioWorkletNode(this.context,'tasktimer-pcm');
      this.node.port.onmessage=({data})=>{if(generation!==this.generation)return;const take=Math.min(data.length,60*this.rate-this.length);if(take>0){this.parts.push(data.slice(0,take));this.length+=take;}};
      this.source.connect(this.node);this.node.connect(this.context.destination);
      await this.context.resume();
      this.timer=setTimeout(()=>{this.finishCapture().then(()=>onAutoStop()).catch(onError);},60_000);
    } catch(error){this.cancel();throw error;}
  }
  async finishCapture() {
    clearTimeout(this.timer);
    this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
    this.source?.disconnect();this.node?.disconnect();
    const context=this.context;this.context=null;if(context && context.state!=='closed')await context.close();
  }
  async stop() {
    if(this.worker)throw new Error('Распознавание уже выполняется');
    const generation=this.generation;
    await this.finishCapture();
    if(generation!==this.generation)throw new DOMException('Отменено','AbortError');
    if(!this.length)throw new Error('Запись пуста. Повторите диктовку.');
    const pcm=new Float32Array(this.length);let offset=0;for(const part of this.parts){pcm.set(part,offset);offset+=part.length;}this.parts=[];this.length=0;
    return new Promise((resolve,reject)=>{
      const worker=this.worker=new Worker('/voice-worker.mjs');this.reject=reject;
      const cleanup=()=>{clearTimeout(this.decodeTimer);worker.terminate();if(this.worker===worker)this.worker=null;this.reject=null;};
      worker.onmessage=({data})=>{cleanup();data.error?reject(new Error(data.error)):resolve(data.text);};
      worker.onerror=()=>{cleanup();reject(new Error('Не удалось запустить распознавание. Возможно, браузеру не хватает памяти.'));};
      this.decodeTimer=setTimeout(()=>{cleanup();reject(new Error('Распознавание заняло слишком долго. Попробуйте более короткую запись.'));},180_000);
      worker.postMessage({pcm,sampleRate:this.rate},[pcm.buffer]);
    });
  }
  cancel(){++this.generation;clearTimeout(this.timer);clearTimeout(this.decodeTimer);this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.source?.disconnect();this.node?.disconnect();const context=this.context;this.context=null;if(context && context.state!=='closed')context.close().catch(()=>{});this.worker?.terminate();this.worker=null;this.reject?.(new DOMException('Отменено','AbortError'));this.reject=null;this.parts=[];this.length=0;}
}
