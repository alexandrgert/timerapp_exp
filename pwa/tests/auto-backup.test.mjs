import test from 'node:test';import assert from 'node:assert/strict';
import{backupFilename,validateBackupSettings,createBackupScheduler,writeBackupFile}from'../public/auto-backup.mjs';
test('backup filename is local timestamp with milliseconds and settings reject invalid intervals',()=>{
 assert.equal(backupFilename(new Date(2026,10,20,9,7,3,21)),'tasktimer-2026-11-20_09-07-03-021.json');
 for(const minutes of [0,1.5,10081,NaN])assert.throws(()=>validateBackupSettings({enabled:true,minutes,destination:'downloads',nextAt:0}));
});
test('scheduled backups honor interval, latest settings and one catch-up copy',async()=>{
 let now=0,saved=[];let config={enabled:true,minutes:60,destination:'downloads',nextAt:3600000};const scheduler=createBackupScheduler({read:()=>config,write:v=>config=v,save:async name=>saved.push(name),lock:fn=>fn(),now:()=>now});
 await scheduler.tick();assert.equal(saved.length,0);now=10*3600000;await scheduler.tick();assert.equal(saved.length,1);assert.equal(config.nextAt,11*3600000);await scheduler.tick();assert.equal(saved.length,1);config.enabled=false;now=20*3600000;await scheduler.tick();assert.equal(saved.length,1);
});
test('multiple controllers under shared lock save once and failure never advances last backup',async()=>{
 let config={enabled:true,minutes:1,destination:'folder',nextAt:0},calls=0,queue=Promise.resolve(),bad=true;const options={read:()=>config,write:v=>config=v,save:async()=>{calls++;if(bad)throw Error('Disk full');},now:()=>60000,lock:fn=>{const next=queue.then(fn);queue=next.catch(()=>{});return next;}};
 await createBackupScheduler(options).tick();assert.equal(config.lastAt,undefined);bad=false;await Promise.all([createBackupScheduler(options).tick(),createBackupScheduler(options).tick()]);assert.equal(calls,2);assert.equal(config.lastAt,60000);
});
test('folder writer requires granted permission and closes or aborts a writable file',async()=>{
 let granted=false,closed=0,aborted=0,text='',fail=false;const directory={queryPermission:async()=>granted?'granted':'prompt',getFileHandle:async(name,options)=>{assert.ok(name.endsWith('.json'));assert.equal(options.create,true);return{createWritable:async()=>({write:async value=>{text=value;if(fail)throw Error('Disk full');},close:async()=>closed++,abort:async()=>aborted++})};}};
 await assert.rejects(writeBackupFile(directory,'copy.json','{}'),/Разрешите/);assert.equal(text,'');granted=true;await writeBackupFile(directory,'copy.json','{"tasks":[]}');assert.equal(closed,1);fail=true;await assert.rejects(writeBackupFile(directory,'copy2.json','{}'),/Не удалось/);assert.equal(aborted,1);
});
test('pending picker defers due backups including lock waits and does not acknowledge deferred writes',async()=>{
 let paused=true,config={enabled:true,minutes:1,destination:'downloads',nextAt:0},calls=0,defer=true,status=[];
 const scheduler=createBackupScheduler({read:()=>config,write:v=>config=v,now:()=>60000,paused:()=>paused,lock:fn=>fn(),save:async()=>{calls++;return defer?false:undefined;},status:v=>status.push(v)});
 await scheduler.tick();assert.equal(calls,0);paused=false;await scheduler.tick();assert.equal(calls,1);assert.equal(config.lastAt,undefined);assert.deepEqual(status,[]);defer=false;await scheduler.tick();assert.equal(config.lastAt,60000);
 const waiting=createBackupScheduler({read:()=>({...config,nextAt:0}),write:()=>assert.fail('must not acknowledge'),now:()=>60000,paused:()=>paused,lock:async fn=>{paused=true;await fn();},save:()=>assert.fail('must not save while picker open')});await waiting.tick();
});
