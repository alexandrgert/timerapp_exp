'use strict';
// Explicit CI integration check. Starts real TCP HTTP and real Service Workers.
// Not matched by npm test. Never substitute route fulfillment for these checks.
if (!process.env.TASKTIMER_LIVE_CHECK_CHILD) {
  const {spawn}=require('node:child_process');
  const child=spawn(process.execPath,[__filename],{stdio:'inherit',detached:process.platform!=='win32',env:{...process.env,TASKTIMER_LIVE_CHECK_CHILD:'1'}});
  let expired=false;
  const kill=()=>{try{process.platform==='win32'?child.kill('SIGKILL'):process.kill(-child.pid,'SIGKILL');}catch{}};
  const watchdog=setTimeout(()=>{expired=true;console.error('Real SW check exceeded external 110 second deadline');kill();},110000);
  child.on('error',error=>{clearTimeout(watchdog);console.error(error.message);process.exitCode=1;});
  child.on('exit',code=>{clearTimeout(watchdog);kill();process.exitCode=expired?124:code??1;});
} else {
  const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),net=require('node:net');
  const {spawn}=require('node:child_process'),{chromium}=require('playwright'),assert=require('node:assert/strict');
  const report={passed:false,checks:[],kind:'real-loopback-service-worker',publicHttps:false,physicalPhone:false};
  let directory,browser,server,serverError='';
  const reportPath=process.env.TASKTIMER_LIVE_REPORT||path.resolve(__dirname,'../live-offline-report.json');
  async function availablePort(){const probe=net.createServer();await new Promise((resolve,reject)=>{probe.once('error',reject);probe.listen(0,'127.0.0.1',resolve);});const port=probe.address().port;await new Promise((resolve,reject)=>probe.close(error=>error?reject(error):resolve()));return port;}
  async function waitForServer(origin){for(let n=0;n<100;n++){if(server.exitCode!==null)throw Error('HTTP server exited: '+serverError);try{if((await fetch(origin+'/health',{signal:AbortSignal.timeout(500)})).ok)return;}catch{}await new Promise(resolve=>setTimeout(resolve,50));}throw Error('Real TCP server unavailable: '+serverError);}
  async function snapshot(page){return page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const repo=await openRepository();try{return await repo.read();}finally{repo.close();}});}
  (async()=>{
    directory=await fs.mkdtemp(path.join(os.tmpdir(),'tasktimer-real-sw-'));
    await fs.cp(path.resolve(__dirname,'../public'),path.join(directory,'public'),{recursive:true});
    await fs.copyFile(path.resolve(__dirname,'../server.cjs'),path.join(directory,'server.cjs'));
    const data=path.join(directory,'data');await fs.mkdir(data);const port=await availablePort(),origin=`http://127.0.0.1:${port}`;
    server=spawn(process.execPath,[path.join(directory,'server.cjs')],{env:{...process.env,PORT:String(port),CLOUDCLI_DATA_DIR:data},stdio:['ignore','ignore','pipe']});
    server.stderr.on('data',chunk=>{serverError=(serverError+chunk.toString()).slice(-4000);});await waitForServer(origin);
    browser=await chromium.launch({headless:true,timeout:15000,args:['--no-sandbox','--disable-dev-shm-usage']});
    const context=await browser.newContext({serviceWorkers:'allow'});context.setDefaultTimeout(15000);
    const page=await context.newPage();await page.goto(origin,{waitUntil:'domcontentloaded'});assert.equal(await page.evaluate(()=>window.isSecureContext),true);
    await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));await page.evaluate(()=>navigator.serviceWorker.ready);
    report.checks.push('actual service worker installation and control');
    await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('Offline integration');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.getByTestId('task-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#active-timer')?.hidden===false);
    const before=await snapshot(page);assert.equal(before.tasks[0].sessions.length,1);assert.equal(before.tasks[0].sessions[0].ended_at,null);
    await context.setOffline(true);await page.reload({waitUntil:'domcontentloaded'});await page.getByTestId('task-row').waitFor();
    const offline=await snapshot(page);assert.equal(offline.tasks[0].id,before.tasks[0].id);assert.deepEqual(offline.tasks[0].sessions,before.tasks[0].sessions);
    report.checks.push('offline reload from real shell cache preserves active timer');
    await context.setOffline(false);
    await fs.appendFile(path.join(directory,'public/app.mjs'),'\nglobalThis.__tasktimerLiveUpdateMarker="accepted-v2";\n');
    await page.evaluate(async()=>{const reg=await navigator.serviceWorker.getRegistration();await reg.update();});
    await page.waitForFunction(async()=>Boolean((await navigator.serviceWorker.getRegistration())?.waiting));
    assert.equal(await page.evaluate(()=>globalThis.__tasktimerLiveUpdateMarker),undefined);
    report.checks.push('new worker waits without replacing running version');
    await page.locator('#settings-button').click();page.once('dialog',dialog=>dialog.accept());
    await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),page.locator('[data-pwa-update]').click()]);
    await page.waitForFunction(()=>globalThis.__tasktimerLiveUpdateMarker==='accepted-v2');await page.getByTestId('task-row').waitFor();
    const updated=await snapshot(page);assert.equal(updated.tasks[0].id,before.tasks[0].id);assert.deepEqual(updated.tasks[0].sessions,before.tasks[0].sessions);
    report.checks.push('explicit accepted update activates new shell and preserves timer');
    await context.setOffline(true);await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>globalThis.__tasktimerLiveUpdateMarker==='accepted-v2');await page.getByTestId('task-row').waitFor();
    assert.deepEqual((await snapshot(page)).tasks[0].sessions,before.tasks[0].sessions);
    report.checks.push('updated shell reloads offline with original active session');report.passed=true;
    console.log('PASS real Service Worker offline/reload/accepted-update checks');
  })().catch(error=>{report.error=error.stack||error.message;console.error(report.error);process.exitCode=1;}).finally(async()=>{
    try{await fs.writeFile(reportPath,JSON.stringify(report,null,2));}catch(error){console.error('Cannot save SW report:',error.message);process.exitCode=1;}
    try{await browser?.close();}finally{server?.kill('SIGTERM');if(directory)await fs.rm(directory,{recursive:true,force:true});}
  });
}
