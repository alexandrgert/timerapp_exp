// External watchdog kills the entire browser process group if JS/browser becomes unresponsive.
if (!process.env.TASKTIMER_VOICE_CHECK_CHILD) {
 const {spawn}=require('node:child_process');
 const child=spawn(process.execPath,[__filename,...process.argv.slice(2)],{stdio:'inherit',detached:process.platform!=='win32',env:{...process.env,TASKTIMER_VOICE_CHECK_CHILD:'1'}});
 const kill=()=>{try{process.platform==='win32'?child.kill('SIGKILL'):process.kill(-child.pid,'SIGKILL');}catch{}};
 const timer=setTimeout(()=>{console.error('Voice check exceeded 180 second external deadline');kill();},180000);
 child.on('exit',(code,signal)=>{clearTimeout(timer);kill();process.exitCode=code??1;});
 child.on('error',error=>{clearTimeout(timer);console.error(error.message);process.exitCode=1;});
} else {
// Explicit integration check: node tests/voice-inference.check.cjs /path/to/pinned-model-files
// Model files + test_wavs-0.wav must be downloaded from the pinned official repository.
const {chromium}=require('playwright'),fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const modelDir=process.argv[2];if(!modelDir)throw new Error('Pass directory with pinned RU model and test_wavs-0.wav');
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--single-process','--no-zygote','--disable-gpu']});
 try{
 const context=await browser.newContext({serviceWorkers:'block'});
 await context.route('https://tasktimer.test/**',async route=>{const p=new URL(route.request().url()).pathname;if(p==='/'){await route.fulfill({body:'<!doctype html><title>Voice integration</title>',contentType:'text/html'});return;}const body=await fs.readFile(path.resolve(__dirname,'../public','.'+p));await route.fulfill({body,contentType:p.endsWith('.wasm')?'application/wasm':'text/javascript'});});
 let requests=0;
 await context.route('https://huggingface.co/**',async route=>{requests++;const file=new URL(route.request().url()).pathname.split('/').pop();await route.fulfill({body:await fs.readFile(path.join(modelDir,file)),contentType:'application/octet-stream'});});
 const page=await context.newPage();page.on('console',msg=>console.log('browser',msg.text()));await page.goto('https://tasktimer.test');
 await page.evaluate(async()=>{const voice=await import('/voice.mjs');await voice.installVoice();if(!await voice.voiceReady())throw new Error('Not ready');});
 assert.equal(requests,4);
 await context.unroute('https://huggingface.co/**');await context.route('https://huggingface.co/**',route=>route.abort());
 const wav=await fs.readFile(path.join(modelDir,'test_wavs-0.wav'));let at=12;while(wav.toString('ascii',at,at+4)!=='data')at+=8+wav.readUInt32LE(at+4);const pcm=Array.from({length:wav.readUInt32LE(at+4)/2},(_,i)=>wav.readInt16LE(at+8+i*2)/32768);
 const text=await page.evaluate(pcm=>new Promise((resolve,reject)=>{const worker=new Worker('/voice-worker.mjs');const timer=setTimeout(()=>{worker.terminate();reject(new Error('timeout'));},120000);worker.onerror=e=>{clearTimeout(timer);worker.terminate();reject(new Error(e.message));};worker.onmessage=({data})=>{clearTimeout(timer);worker.terminate();data.error?reject(new Error(data.error)):resolve(data.text);};worker.postMessage({pcm:new Float32Array(pcm),sampleRate:16000});}),pcm);
 assert.equal(text,'я тебя люблю');console.log('PASS real Chromium worker offline RU inference:',text);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

}
