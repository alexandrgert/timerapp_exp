const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require('playwright');
const publicRoot=path.resolve(__dirname,'../public');
const origin='https://tasktimer.test';
const mime={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webmanifest':'application/manifest+json'};
let browser,launchFailed=false;
test.beforeEach(async()=>{if(launchFailed)throw new Error('Chromium startup failed earlier; no automatic retries');try{browser=await chromium.launch({timeout:15000,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--single-process','--no-zygote','--disable-gpu']});}catch(error){launchFailed=true;throw error;}});
test.afterEach(async()=>browser?.close());
async function setup({voiceMock}={}){const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:'Europe/Moscow',serviceWorkers:'block'});await context.route(`${origin}/**`,async route=>{const url=new URL(route.request().url()),name=url.pathname==='/'?'index.html':url.pathname.slice(1);try{const body=await fs.readFile(path.join(publicRoot,name));await route.fulfill({body,contentType:mime[path.extname(name)]||'application/octet-stream'});}catch{await route.fulfill({status:404,body:'not found'});}});if(voiceMock)await context.route(`${origin}/voice.mjs`,route=>route.fulfill({body:voiceMock,contentType:'text/javascript'}));const page=await context.newPage();await page.goto(origin);await page.getByText('С чего начнём?').waitFor();return {context,page};}
async function create(page,title){await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill(title);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});}
async function read(page){return page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return await r.read();}finally{r.close();}});}
test('mobile CRUD, validation retains input, cancel, history, export/import and deletion',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Проект PWA');assert.equal(await page.getByTestId('task-row').count(),1);
 assert.equal((await read(page)).tasks[0].priority,4);
 await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T23:30');await page.getByTestId('session-end').fill('2026-09-29T22:30');await page.getByTestId('session-comment').fill('Через полночь');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.equal(await page.getByTestId('session-comment').inputValue(),'Через полночь');
 await page.getByTestId('session-end').fill('2026-09-30T00:30');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal(await page.getByTestId('session').count(),1);assert.equal((await read(page)).tasks[0].sessions[0].comment,'Через полночь');
 await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-comment').fill('Отмена');await page.locator('#editor-dialog').getByRole('button',{name:'Отмена',exact:true}).click();assert.equal((await read(page)).tasks[0].sessions[0].comment,'Через полночь');
 await page.getByTestId('task-toggle').click();await page.getByTestId('live-clock').waitFor();await page.reload();await page.getByTestId('live-clock').waitFor();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).click();await page.locator('#active-timer').waitFor({state:'hidden'});
 const data=await read(page);await page.getByRole('button',{name:'Настройки и резервные копии'}).click();const downloading=page.waitForEvent('download');await page.getByTestId('export').click();const download=await downloading;assert.match(download.suggestedFilename(),/^tasktimer-.*\.json$/);
 await page.getByTestId('import').setInputFiles({name:'copy.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});await page.getByTestId('confirm').click();await page.locator('#confirm-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks[0].id,data.tasks[0].id);await page.locator('#settings-dialog').getByRole('button',{name:'Закрыть'}).click();
 await page.locator('.task-select').click();await page.locator('.detail-actions').getByRole('button',{name:'Удалить',exact:true}).click();await page.getByTestId('confirm').click();await page.locator('#confirm-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.length,0);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile has no horizontal overflow');
 }finally{await context.close();}
});
test('comment edit preserves exact imported timestamps and metadata',async()=>{const {context,page}=await setup();try{await create(page,'Точность');await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();const s=await r.read();s.tasks[0].sessions.push({id:'precision',started_at:'2026-09-28T10:00:00.123456+03:00',ended_at:'2026-09-28T11:00:00.987654+03:00',comment:'До',bitrix_record_id:'123'});await r.dispatch({type:'replaceState',values:s});r.close();});await page.getByTestId('session').waitFor();await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-comment').fill('После');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const session=(await read(page)).tasks[0].sessions[0];assert.equal(session.started_at,'2026-09-28T10:00:00.123456+03:00');assert.equal(session.ended_at,'2026-09-28T11:00:00.987654+03:00');assert.equal(session.bitrix_record_id,'123');assert.equal(session.comment,'После');}finally{await context.close();}});
test('two tabs refresh and focus expiration closes exactly at saved deadline after reload',async()=>{const {context,page}=await setup();try{await create(page,'Фокус');const second=await context.newPage();await second.goto(origin);await second.getByTestId('task-row').waitFor();await page.locator('#task-details').getByRole('button',{name:'Концентрация',exact:true}).click();assert.equal(await page.getByTestId('focus-task').inputValue(),(await read(page)).tasks[0].id);await page.getByTestId('focus-minutes').fill('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await second.getByTestId('live-clock').waitFor();const started=await read(page);assert.ok(started.focus);const deadline=started.focus.ends_at;
 await page.clock.install({time:new Date(new Date(deadline).getTime()+1000)});await page.reload();await page.locator('#task-list .task-row').waitFor();assert.equal((await read(page)).focus,null);assert.equal((await read(page)).tasks[0].sessions[0].ended_at,deadline);await second.locator('#active-timer').waitFor({state:'hidden'});assert.equal((await read(second)).tasks[0].status,'paused');
 }finally{await context.close();}});
test('storage quota error retains form and existing data, retry commits once',async()=>{const {context,page}=await setup();try{await create(page,'Сохранённая');await page.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){IDBObjectStore.prototype.put=original;throw new DOMException('Недостаточно места на устройстве','QuotaExceededError');};});await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('После ошибки');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.equal(await page.getByTestId('task-title').inputValue(),'После ошибки');assert.equal((await read(page)).tasks.length,1);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.length,2);}finally{await context.close();}});
test('comment-only save does not overwrite interval edited in another tab',async()=>{const {context,page}=await setup();try{await create(page,'Совместная правка');await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T10:00');await page.getByTestId('session-end').fill('2026-09-29T11:00');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const second=await context.newPage();await second.goto(origin);await second.locator('.task-select').click();await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-comment').fill('Комментарий другой вкладки');await second.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await second.getByTestId('session-start').fill('2026-09-29T09:30');await second.getByTestId('save').click();await second.locator('#editor-dialog').waitFor({state:'hidden'});const updated=(await read(second)).tasks[0].sessions[0].started_at;await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const result=(await read(page)).tasks[0].sessions[0];assert.equal(result.started_at,updated);assert.equal(result.comment,'Комментарий другой вкладки');}finally{await context.close();}});
test('time-only and title-only edits preserve newer untouched fields from another tab',async()=>{const {context,page}=await setup();try{await create(page,'Исходное название');await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T10:00');await page.getByTestId('session-end').fill('2026-09-29T11:00');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const second=await context.newPage();await second.goto(origin);await second.locator('.task-select').click();await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-start').fill('2026-09-29T09:00');await second.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await second.getByTestId('session-comment').fill('Новый комментарий');await second.getByTestId('save').click();await second.locator('#editor-dialog').waitFor({state:'hidden'});await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks[0].sessions[0].comment,'Новый комментарий');await page.locator('.detail-actions').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('task-title').fill('Новое название');await second.locator('.detail-actions').getByRole('button',{name:'Изменить',exact:true}).click();await second.locator('textarea[name=description]').fill('Новое описание');await second.locator('[name=priority]').selectOption('2');await second.getByTestId('save').click();await second.locator('#editor-dialog').waitFor({state:'hidden'});await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const task=(await read(page)).tasks[0];assert.equal(task.title,'Новое название');assert.equal(task.description,'Новое описание');assert.equal(task.priority,2);}finally{await context.close();}});

test('WebDAV merges concurrent local edits, backs up migration and preserves deletion',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Локальная');
 const result=await page.evaluate(async()=>{
  const {openRepository}=await import('/repository.mjs');const {synchronize}=await import('/sync-controller.mjs');const {changeEntity}=await import('/sync-protocol.mjs');
  const r=await openRepository();const first=await r.read();const id=first.tasks[0].id;await r.enableSync();const initial=await r.mergeSync(null);let writes=0;
  const remote=changeEntity(initial.document,'remote',['task',id],{title:'С компьютера'});
  const client={read:async()=>{await r.dispatch({type:'updateTask',taskId:id,values:{description:'Во время сети'}});return {body:JSON.stringify(remote),etag:'"one"'};},write:async(body)=>{writes++;JSON.parse(body);await r.dispatch({type:'updateTask',taskId:id,values:{priority:2}});}};
  await synchronize(r,client);const merged=await r.read();const backup=await r.migrationBackup();
  await r.dispatch({type:'deleteTask',taskId:id});await r.mergeSync(remote);const deleted=await r.read();r.close();return {merged,backup,deleted,writes};
 });
 assert.equal(result.merged.tasks[0].title,'С компьютера');assert.equal(result.merged.tasks[0].description,'Во время сети');assert.equal(result.merged.tasks[0].priority,2);assert.equal(result.backup.tasks[0].title,'Локальная');assert.equal(result.deleted.tasks.length,0);assert.equal(result.writes,1);
 }finally{await context.close();}
});

test('WebDAV concurrent timers retained until explicit choice and 412 retries bounded',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Первая');await create(page,'Вторая');
 const result=await page.evaluate(async()=>{
  const {openRepository}=await import('/repository.mjs');const {synchronize}=await import('/sync-controller.mjs');const {changeEntity}=await import('/sync-protocol.mjs');
  const r=await openRepository();await r.enableSync();const start=await r.mergeSync(null);const ids=start.state.tasks.map(t=>t.id);const now=new Date(Date.now()-60000).toISOString();
  let remote=changeEntity(start.document,'remote',['session',ids[0],'one'],{interval:{started_at:now,ended_at:null},comment:'',bitrix_record_id:null});
  remote=changeEntity(remote,'remote',['session',ids[1],'two'],{interval:{started_at:now,ended_at:null},comment:'',bitrix_record_id:null});
  const blocked=await r.mergeSync(remote);let prevented=false;try{await r.dispatch({type:'createTask',values:{title:'must not write'}});}catch{prevented=true;}
  const chosen=await r.keepActive(ids[0],'one',blocked.state.sync.activeSessions);let attempts=0;try{await synchronize(r,{read:async()=>({body:JSON.stringify(remote),etag:'"one"'}),write:async()=>{attempts++;throw Object.assign(new Error('conflict'),{code:412});}});}catch{}
  r.close();return {blocked:blocked.state,prevented,chosen,attempts};
 });
 assert.equal(result.blocked.sync.activeSessions.length,2);assert.equal(result.prevented,true);assert.equal(result.chosen.tasks.flatMap(t=>t.sessions).filter(s=>s.ended_at===null).length,1);assert.equal(result.chosen.tasks.flatMap(t=>t.sessions).length,2);assert.equal(result.attempts,3);
 }finally{await context.close();}
});


test('voice controls append editable dictation and cancellation preserves original field',async()=>{
 const voiceMock=`export const VOICE_BYTES=100;export async function voiceReady(){return true;}export async function installVoice(){}export async function removeVoice(){}export class VoiceDictation{async start(){}async stop(){return 'новые слова';}cancel(){}}`;
 const {context,page}=await setup({voiceMock});try{
 await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('Начало');
 await page.getByRole('button',{name:'Диктовать: название',exact:true}).click();await page.locator('#voice-record').click();await page.locator('#voice-stop').click();await page.locator('#voice-add').waitFor({state:'visible'});await page.locator('#voice-result').fill('проверенный текст');await page.locator('#voice-add').click();
 assert.equal(await page.getByTestId('task-title').inputValue(),'Начало проверенный текст');
 await page.getByRole('button',{name:'Диктовать: название',exact:true}).click();await page.locator('#voice-record').click();await page.locator('#voice-cancel').click();assert.equal(await page.getByTestId('task-title').inputValue(),'Начало проверенный текст');
 await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks[0].title,'Начало проверенный текст');
 }finally{await context.close();}
});

test('PWA priority uses canonical daily map and desktop clear returns priority four',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Приоритет');const result=await page.evaluate(async()=>{
 const {openRepository}=await import('/repository.mjs');const {changeEntity,projectTasks}=await import('/sync-protocol.mjs');const r=await openRepository();const id=(await r.read()).tasks[0].id;await r.dispatch({type:'updateTask',taskId:id,values:{priority:1}});await r.enableSync();const initial=await r.mergeSync(null);const task=projectTasks(initial.document).tasks[0];const remote=changeEntity(initial.document,'desktop',[ 'task',id],{daily_priorities:{},keep_priority:false});await r.mergeSync(remote);const cleared=await r.read();r.close();return {task,cleared};
 });assert.equal(result.task.daily_priorities[result.task.day],1);assert.equal('priority'in result.task,false);assert.equal(result.cleared.tasks[0].priority,4);
 }finally{await context.close();}
});

test('stale same-field form preserves both draft and current value until explicit overwrite',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Исходное');await page.getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('task-title').fill('Мой черновик');
 await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();const s=await r.read();await r.dispatch({type:'updateTask',taskId:s.tasks[0].id,values:{title:'Другая вкладка'}});r.close();});
 await page.getByTestId('save').click();await page.locator('#editor-overwrite').waitFor({state:'visible'});assert.equal(await page.getByTestId('task-title').inputValue(),'Мой черновик');assert.equal((await read(page)).tasks[0].title,'Другая вкладка');assert.match(await page.locator('#editor-error').textContent(),/Другая вкладка/);
 await page.locator('#editor-overwrite').click();await page.getByTestId('confirm').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks[0].title,'Мой черновик');
 }finally{await context.close();}
});

test('portable synchronized backup keeps hidden conflicts and tombstones without device identity',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Сохранить');await create(page,'Удалить');const result=await page.evaluate(async()=>{
  const {openRepository}=await import('/repository.mjs');const {changeEntity,mergeDocuments,projectDocument}=await import('/sync-protocol.mjs');const r=await openRepository();await r.enableSync();const initial=await r.mergeSync(null);const[one,two]=initial.state.tasks;const a=changeEntity(initial.document,'left',['task',one.id],{title:'Левый'});const b=changeEntity(initial.document,'right',['task',one.id],{title:'Правый'});await r.mergeSync(mergeDocuments(a,b));await r.dispatch({type:'deleteTask',taskId:two.id});const backup=await r.exportBackup();const restored=await openRepository({name:'restored-copy'});await restored.dispatch({type:'replaceState',values:backup});const after=await restored.mergeSync(null);const projected=projectDocument(after.document);r.close();restored.close();return {backup,conflicts:projected.conflicts.length,deleted:projected.entities.filter(e=>e.deleted).length};
 });assert.ok(result.backup.syncDocument);assert.equal('sync'in result.backup,false);assert.equal('actor'in result.backup,false);assert.equal(result.conflicts,1);assert.equal(result.deleted,1);
 }finally{await context.close();}
});

test('remote legacy bootstrap is backed up once without copying legacy settings',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Legacy');const result=await page.evaluate(async()=>{
 const {openRepository}=await import('/repository.mjs');const {synchronize}=await import('/sync-controller.mjs');const r=await openRepository();const first=await r.read();const legacy={tasks:structuredClone(first.tasks),customEnvelope:{keep:'yes'}};legacy.tasks[0].title='Remote legacy';let reads=0;const client={read:async()=>null,write:async()=>{}};const legacyClient={readLegacy:async()=>{reads++;return {body:JSON.stringify(legacy)};}};await synchronize(r,client,{legacyClient});const one=await r.mergeSync(null);legacy.tasks[0].title='Must not reimport';await synchronize(r,client,{legacyClient});const two=await r.mergeSync(null);const backup=await r.exportBackup();r.close();return {one:one.document.ops.length,two:two.document.ops.length,backup,reads};
 });assert.equal(result.one,result.two);assert.equal('customEnvelope'in result.backup.legacyRemoteSnapshot,false);assert.equal(result.backup.legacyRemoteSnapshot.tasks[0].title,'Remote legacy');
 }finally{await context.close();}
});


test('sync rejects malformed projection and stale conflict/timer choices without discarding changes',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Защита');const result=await page.evaluate(async()=>{
 const {openRepository}=await import('/repository.mjs');const {changeEntity,mergeDocuments}=await import('/sync-protocol.mjs');const r=await openRepository();await r.enableSync();const base=await r.mergeSync(null);const id=base.state.tasks[0].id;
 let malformed=false;try{await r.mergeSync(changeEntity(base.document,'invalid',['task',id],{day:'invalid'}));}catch{malformed=true;}
 const unchanged=(await r.mergeSync(null)).document.ops.length===base.document.ops.length;
 const a=changeEntity(base.document,'a',['task',id],{title:'A'}),b=changeEntity(base.document,'b',['task',id],{title:'B'});const first=await r.mergeSync(mergeDocuments(a,b));const conflict=first.state.sync.conflicts[0];await r.mergeSync(changeEntity(base.document,'c',['task',id],{title:'C'}));let staleConflict=false;try{await r.resolveSync(conflict.entity,conflict.field,conflict.candidates[0].value,conflict.candidates);}catch{staleConflict=true;}
 const interval={started_at:new Date(Date.now()-60000).toISOString(),ended_at:null};let doc=(await r.mergeSync(null)).document;for(const sid of ['one','two'])doc=changeEntity(doc,'timer',['session',id,sid],{interval,comment:'',bitrix_record_id:null});const timers=await r.mergeSync(doc);doc=changeEntity(doc,'timer',['session',id,'three'],{interval,comment:'',bitrix_record_id:null});await r.mergeSync(doc);let staleTimers=false;try{await r.keepActive(id,'one',timers.state.sync.activeSessions);}catch{staleTimers=true;}
 const latest=await r.read();r.close();return {malformed,unchanged,staleConflict,staleTimers,active:latest.sync.activeSessions.length,conflicts:latest.sync.conflicts[0].candidates.length};
 });assert.deepEqual(result,{malformed:true,unchanged:true,staleConflict:true,staleTimers:true,active:3,conflicts:3});
 }finally{await context.close();}
});

test('known v2 target never reimports stale legacy after remote deletion; another target can migrate',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Миграция');const result=await page.evaluate(async()=>{
 const {openRepository}=await import('/repository.mjs');const {synchronize}=await import('/sync-controller.mjs');const r=await openRepository();await r.enableSync();const doc=(await r.mergeSync(null)).document;let exists=true,legacyReads=0;const client={read:async()=>exists?{body:JSON.stringify(doc),etag:'"1"'}:null,write:async()=>{}};const legacyClient={readLegacy:async()=>{legacyReads++;return {body:'{"tasks":[],"ui":{"private":"not imported"}}'};}};
 await synchronize(r,client,{legacyClient,targetKey:'target-one'});exists=false;await synchronize(r,client,{legacyClient,targetKey:'target-one'});const same=legacyReads;await synchronize(r,client,{legacyClient,targetKey:'target-two'});r.close();return {same,total:legacyReads};
 });assert.deepEqual(result,{same:0,total:1});
 }finally{await context.close();}
});

test('editor refuses hidden concurrent candidate even when projected original remains unchanged',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Первоначальное');
 await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const {changeEntity}=await import('/sync-protocol.mjs');const r=await openRepository();await r.enableSync();const base=await r.mergeSync(null);const id=base.state.tasks[0].id;await r.mergeSync(changeEntity(base.document,'a',['task',id],{title:'Левый'}));globalThis.fixtureBranch=base.document;globalThis.fixtureTask=id;r.close();});
 await page.getByRole('button',{name:'Изменить',exact:true}).click();assert.equal(await page.getByTestId('task-title').inputValue(),'Левый');await page.getByTestId('task-title').fill('Мой черновик');
 await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const {changeEntity}=await import('/sync-protocol.mjs');const r=await openRepository();await r.mergeSync(changeEntity(globalThis.fixtureBranch,'z',['task',globalThis.fixtureTask],{title:'Правый'}));r.close();});
 assert.equal((await read(page)).tasks[0].title,'Левый');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.match(await page.locator('#editor-error').textContent(),/Сначала разрешите конфликт/);assert.equal(await page.getByTestId('task-title').inputValue(),'Мой черновик');const current=await read(page);assert.equal(current.tasks[0].title,'Левый');assert.equal(current.sync.conflicts[0].candidates.length,2);
 }finally{await context.close();}
});
test('standalone focus starts empty, survives reload, expires without task time and can stop',async()=>{
 const {context,page}=await setup();try{
 await page.getByTestId('start-focus').click();assert.equal(await page.getByTestId('focus-task').inputValue(),'');
 await page.getByTestId('focus-minutes').fill('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 const before=await read(page);assert.equal(before.focus.taskId,null);assert.deepEqual(before.tasks,[]);
 await page.reload();await page.getByTestId('focus-clock').waitFor();assert.deepEqual((await read(page)).focus,before.focus);
 await page.clock.install({time:new Date(Date.parse(before.focus.ends_at)+1000)});await page.reload();await page.getByTestId('start-focus').waitFor();assert.equal((await read(page)).focus,null);assert.deepEqual((await read(page)).tasks,[]);await page.locator('#standalone-focus').waitFor({state:'hidden'});
 await page.getByTestId('start-focus').click();await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.locator('#standalone-focus [data-action="stopFocus"]').click();await page.locator('#standalone-focus').waitFor({state:'hidden'});assert.deepEqual((await read(page)).tasks,[]);
 }finally{await context.close();}
});
test('standalone focus survives sync projection and keeps concurrent task timer independent',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Независимая задача');await page.getByTestId('task-toggle').click();await page.getByTestId('live-clock').waitFor();
 await page.getByTestId('start-focus').click();assert.equal(await page.getByTestId('focus-task').inputValue(),'');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 const before=await read(page);assert.equal(before.focus.taskId,null);
 await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{await r.enableSync();const b=await r.exportBackup();await r.mergeSync(b.syncDocument);}finally{r.close();}});
 await page.reload();await page.getByTestId('focus-clock').waitFor();await page.getByTestId('live-clock').waitFor();assert.deepEqual((await read(page)).focus,before.focus);assert.deepEqual((await read(page)).tasks[0].sessions,before.tasks[0].sessions);
 assert.notEqual(await page.getByTestId('focus-clock').textContent(),await page.getByTestId('live-clock').textContent());
 await page.locator('#standalone-focus [data-action="stopFocus"]').click();await page.locator('#standalone-focus').waitFor({state:'hidden'});assert.deepEqual((await read(page)).tasks[0].sessions,before.tasks[0].sessions);await page.getByTestId('live-clock').waitFor();
 }finally{await context.close();}
});
test('global focus optionally selects task and accounts time only for that task',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Выбранная');const taskId=(await read(page)).tasks[0].id;
 await page.getByTestId('start-focus').click();await page.getByTestId('focus-task').selectOption(taskId);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.getByTestId('live-clock').waitFor();
 const state=await read(page);assert.equal(state.focus.taskId,taskId);assert.equal(state.tasks[0].sessions.length,1);assert.equal(state.tasks[0].sessions[0].ended_at,null);await page.locator('#standalone-focus').waitFor({state:'hidden'});
 }finally{await context.close();}
});
test('standalone focus remains local through unresolved concurrent remote sessions',async()=>{
 const {context,page}=await setup();try{
 const result=await page.evaluate(async()=>{
  const {openRepository}=await import('/repository.mjs');const p=await import('/sync-protocol.mjs');const r=await openRepository();
  try{
   await r.dispatch({type:'createTask',values:{title:'Conflict'}});await r.enableSync();const backup=await r.exportBackup();const taskId=backup.tasks[0].id;const now=new Date().toISOString();
   let remote=p.changeEntity(backup.syncDocument,'remote-a',['session',taskId,'a'],{interval:{started_at:now,ended_at:null},comment:''});
   remote=p.changeEntity(remote,'remote-b',['session',taskId,'b'],{interval:{started_at:now,ended_at:null},comment:''});await r.mergeSync(remote);
   const before=await r.exportBackup();const projectionError=(await r.read()).sync.projectionError;await r.dispatch({type:'startFocus',taskId:null,values:{minutes:1}});const started=await r.exportBackup();await r.dispatch({type:'stopFocus'});const stopped=await r.exportBackup();
   await r.dispatch({type:'startFocus',taskId:null,values:{minutes:1}});return {before,started,stopped,projectionError,deadline:(await r.read()).focus.ends_at};
  }finally{r.close();}
 });
 assert.ok(result.projectionError);assert.equal(result.started.focus.taskId,null);assert.equal(result.stopped.focus,null);assert.deepEqual(result.started.tasks,result.before.tasks);assert.deepEqual(result.stopped.syncDocument,result.before.syncDocument);
 await page.clock.install({time:new Date(Date.parse(result.deadline)+1000)});await page.reload();const expired=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{return await r.exportBackup();}finally{r.close();}});assert.equal(expired.focus,null);assert.deepEqual(expired.syncDocument,result.before.syncDocument);assert.deepEqual(expired.tasks,result.before.tasks);
 }finally{await context.close();}
});
