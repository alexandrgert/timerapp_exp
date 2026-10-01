/* Classic worker: upstream Emscripten glue uses importScripts and global Module. */
self.onmessage=async({data})=>{
  try {
    const {VOICE_CACHE,VOICE_FILES,verifyVoiceFile}=await import('./voice-assets.mjs');
    const cache=await caches.open(VOICE_CACHE),files=new Map();
    for(const file of VOICE_FILES){const response=await cache.match(file.url);if(!response)throw new Error('Модель удалена из хранилища браузера. Загрузите её заново.');files.set(file.name,await verifyVoiceFile(file,await response.arrayBuffer()));}
    const runtime=new Promise((resolve,reject)=>{
      self.Module={wasmBinary:files.get('sherpa-onnx-wasm-main-vad-asr.wasm'),getPreloadedPackage:()=>new ArrayBuffer(0),onRuntimeInitialized:resolve,onAbort:()=>reject(new Error('Недостаточно памяти или WASM SIMD не поддерживается браузером.'))};
    });
    importScripts('/voice-assets/sherpa-onnx-asr.js','/voice-assets/sherpa-onnx-wasm-main-vad-asr.js');
    await runtime;
    for(const file of VOICE_FILES.filter(f=>!f.runtime))Module.FS_createDataFile('/ru-'+file.name,null,new Uint8Array(files.get(file.name)),true,false,true);
    files.clear();
    const recognizer=new OfflineRecognizer({modelConfig:{transducer:{encoder:'/ru-encoder.int8.onnx',decoder:'/ru-decoder.onnx',joiner:'/ru-joiner.int8.onnx'},tokens:'/ru-tokens.txt',modelType:'transducer',numThreads:1,debug:0}},Module);
    if(!recognizer.handle)throw new Error('Не удалось открыть русскую модель');
    const stream=recognizer.createStream();
    try{stream.acceptWaveform(data.sampleRate,data.pcm);recognizer.decode(stream);self.postMessage({text:recognizer.getResult(stream).text.trim()});}
    finally{stream.free();recognizer.free();}
  }catch(error){self.postMessage({error:error.message||'Ошибка офлайн-распознавания'});}
};
