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
async function reload(page){const accept=dialog=>{assert.equal(dialog.type(),'beforeunload');return dialog.accept();};page.on('dialog',accept);try{await page.reload();}finally{page.off('dialog',accept);}}
async function closeDetails(page){if(await page.locator('#details-dialog').isVisible())await page.locator('#details-dialog .close-dialog').click();}
async function create(page,title){await closeDetails(page);await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill(title);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.locator('.task-select').filter({hasText:title}).click();}
async function read(page){return page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return await r.read();}finally{r.close();}});}
test('mobile CRUD, validation retains input, cancel, history, export/import and deletion',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Проект PWA');assert.equal(await page.getByTestId('task-row').count(),1);
 assert.equal((await read(page)).tasks[0].priority,4);
 await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T23:30');await page.getByTestId('session-end').fill('2026-09-29T22:30');await page.getByTestId('session-comment').fill('Через полночь');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.equal(await page.getByTestId('session-comment').inputValue(),'Через полночь');
 await page.getByTestId('session-end').fill('2026-09-30T00:30');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal(await page.getByTestId('session').count(),1);assert.equal((await read(page)).tasks[0].sessions[0].comment,'Через полночь');
 await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-comment').fill('Отмена');await page.locator('#editor-dialog').getByRole('button',{name:'Отмена',exact:true}).click();assert.equal((await read(page)).tasks[0].sessions[0].comment,'Через полночь');
 await closeDetails(page);await page.getByTestId('task-toggle').click();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();await reload(page);await page.getByTestId('live-clock').waitFor();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).click();await page.getByRole('button',{name:'▶ Продолжить',exact:true}).waitFor();
 const data=await read(page);await closeDetails(page);await page.getByRole('button',{name:'Настройки и резервные копии'}).click();const downloading=page.waitForEvent('download');await page.getByTestId('export').click();const download=await downloading;assert.match(download.suggestedFilename(),/^tasktimer-.*\.json$/);
 await page.getByTestId('import').setInputFiles({name:'copy.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});await page.getByTestId('confirm').click();await page.locator('#confirm-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks[0].id,data.tasks[0].id);await page.locator('#settings-dialog').getByRole('button',{name:'Закрыть'}).click();
 await page.locator('.task-select').click();await page.locator('.detail-actions').getByRole('button',{name:'Удалить',exact:true}).click();await page.getByTestId('confirm').click();await page.locator('#confirm-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.length,0);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile has no horizontal overflow');
 }finally{await context.close();}
});
test('comment edit preserves exact imported timestamps and metadata',async()=>{const {context,page}=await setup();try{await create(page,'Точность');await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();const s=await r.read();s.tasks[0].sessions.push({id:'precision',started_at:'2026-09-28T10:00:00.123456+03:00',ended_at:'2026-09-28T11:00:00.987654+03:00',comment:'До',bitrix_record_id:'123'});await r.dispatch({type:'replaceState',values:s});r.close();});await page.getByTestId('session').waitFor();await page.getByTestId('session').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('session-comment').fill('После');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const session=(await read(page)).tasks[0].sessions[0];assert.equal(session.started_at,'2026-09-28T10:00:00.123456+03:00');assert.equal(session.ended_at,'2026-09-28T11:00:00.987654+03:00');assert.equal(session.bitrix_record_id,'123');assert.equal(session.comment,'После');}finally{await context.close();}});
test('two tabs refresh and desktop focus expiration offers explicit resume',async()=>{const {context,page}=await setup();try{await create(page,'Фокус');await closeDetails(page);await page.getByTestId('task-toggle').click();const second=await context.newPage();await second.goto(origin);await second.getByTestId('task-row').waitFor();await page.getByTestId('start-focus').click();await page.getByTestId('focus-minutes').fill('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const started=await read(page);const deadline=started.focus.ends_at,focusId=started.focus.taskId,previous=started.focus.previousTaskId;assert.equal(started.tasks.find(t=>t.id===previous).status,'paused');await page.clock.install({time:new Date(Date.parse(deadline)+1000)});await reload(page);await page.locator('#focus-resume').waitFor();const ended=await read(page);assert.equal(ended.focus,null);assert.equal(ended.tasks.find(t=>t.id===focusId).sessions[0].ended_at,deadline);assert.equal(ended.tasks.find(t=>t.id===focusId).status,'completed');await second.locator('#focus-resume').waitFor();assert.equal((await read(second)).focusResumeTaskId,previous);await page.getByRole('button',{name:'Продолжить задачу',exact:true}).click();await page.locator('#focus-resume').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.find(t=>t.id===previous).status,'running');}finally{await context.close();}});
test('storage quota error retains form and existing data, retry commits once',async()=>{const {context,page}=await setup();try{await create(page,'Сохранённая');await page.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){IDBObjectStore.prototype.put=original;throw new DOMException('Недостаточно места на устройстве','QuotaExceededError');};});await closeDetails(page);await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('После ошибки');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.equal(await page.getByTestId('task-title').inputValue(),'После ошибки');assert.equal((await read(page)).tasks.length,1);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.length,2);}finally{await context.close();}});
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
 await closeDetails(page);await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('Начало');
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
 await create(page,'Исходное');await page.locator('.detail-actions').getByRole('button',{name:'Изменить',exact:true}).click();await page.getByTestId('task-title').fill('Мой черновик');
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
 await page.locator('.detail-actions').getByRole('button',{name:'Изменить',exact:true}).click();assert.equal(await page.getByTestId('task-title').inputValue(),'Левый');await page.getByTestId('task-title').fill('Мой черновик');
 await page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const {changeEntity}=await import('/sync-protocol.mjs');const r=await openRepository();await r.mergeSync(changeEntity(globalThis.fixtureBranch,'z',['task',globalThis.fixtureTask],{title:'Правый'}));r.close();});
 assert.equal((await read(page)).tasks[0].title,'Левый');await page.getByTestId('save').click();await page.locator('#editor-error').waitFor({state:'visible'});assert.match(await page.locator('#editor-error').textContent(),/Сначала разрешите конфликт/);assert.equal(await page.getByTestId('task-title').inputValue(),'Мой черновик');const current=await read(page);assert.equal(current.tasks[0].title,'Левый');assert.equal(current.sync.conflicts[0].candidates.length,2);
 }finally{await context.close();}
});
test('desktop focus starts empty, survives reload and records a completed focus task',async()=>{const {context,page}=await setup();try{await page.getByTestId('start-focus').click();await page.getByTestId('focus-minutes').fill('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});const before=await read(page);assert.equal(before.tasks.length,1);assert.equal(before.focus.taskId,before.tasks[0].id);await reload(page);await page.locator('#focus-panel-stop').waitFor();assert.deepEqual((await read(page)).focus,before.focus);await page.clock.install({time:new Date(Date.parse(before.focus.ends_at)+1000)});await reload(page);await page.locator('#focus-panel-start').waitFor();const ended=await read(page);assert.equal(ended.focus,null);assert.equal(ended.tasks[0].status,'completed');assert.equal(ended.tasks[0].sessions[0].ended_at,before.focus.ends_at);}finally{await context.close();}});
test('desktop focus survives sync and manual stop preserves paused task then resumes explicitly',async()=>{const {context,page}=await setup();try{await create(page,'Прежняя задача');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{await r.enableSync();}finally{r.close();}});await page.locator('#focus-panel-start').click();await page.locator('#focus-panel-stop').waitFor();const before=await read(page);assert.equal(before.tasks.length,2);assert.equal(before.tasks.find(t=>t.id===before.focus.previousTaskId).status,'paused');await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{await r.enableSync();const b=await r.exportBackup();await r.mergeSync(b.syncDocument);}finally{r.close();}});await reload(page);await page.locator('#focus-panel-stop').click();await page.locator('#focus-resume').waitFor();const stopped=await read(page);assert.equal(stopped.tasks.find(t=>t.id===before.focus.taskId).status,'completed');assert.deepEqual(stopped.tasks.find(t=>t.id===before.focus.previousTaskId).sessions,before.tasks.find(t=>t.id===before.focus.previousTaskId).sessions);await page.getByRole('button',{name:'Продолжить задачу',exact:true}).click();await page.locator('#focus-resume').waitFor({state:'hidden'});assert.equal((await read(page)).tasks.find(t=>t.id===before.focus.previousTaskId).sessions.length,2);}finally{await context.close();}});
test('desktop focus refuses unresolved concurrent remote sessions without discarding data',async()=>{const {context,page}=await setup();try{const result=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const p=await import('/sync-protocol.mjs');const r=await openRepository();try{await r.dispatch({type:'createTask',values:{title:'Conflict'}});await r.enableSync();const b=await r.exportBackup();let remote=b.syncDocument;const now=new Date().toISOString();for(const sid of ['a','b'])remote=p.changeEntity(remote,'remote-'+sid,['session',b.tasks[0].id,sid],{interval:{started_at:now,ended_at:null},comment:''});await r.mergeSync(remote);const before=await r.exportBackup();let prevented=false;try{await r.dispatch({type:'startFocus',values:{minutes:1}});}catch{prevented=true;}const after=await r.exportBackup();return{before,after,prevented};}finally{r.close();}});assert.equal(result.prevented,true);assert.deepEqual(result.before,result.after);}finally{await context.close();}});

test('desktop parity workspace exposes plan views and priority controls on mobile',async()=>{const {context,page}=await setup();try{await page.getByRole('button',{name:'Сегодня',exact:true}).waitFor({timeout:2000});await create(page,'План дня');await closeDetails(page);await page.locator('[data-select-task]').check();await page.getByRole('button',{name:'Назначить приоритет 1',exact:true}).click();await page.locator('.priority-badge.p1').waitFor();assert.equal(await page.locator('.priority-badge').textContent(),'1');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.waitForTimeout(1100);await page.getByRole('button',{name:'Отчёт дня',exact:true}).click();await page.locator('#report-dialog').waitFor();assert.match(await page.locator('#report-text').inputValue(),/План дня/);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}finally{await context.close();}});

test('date history report retains start-day accounting, result and full printable safe text',async()=>{const {context,page}=await setup();try{await create(page,'Отчёт <img src=x>');await page.locator('.detail-actions [data-action="editTask"]').click();await page.locator('[name=result]').fill('Готово <script>bad</script>');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T23:30');await page.getByTestId('session-end').fill('2026-09-30T00:30');await page.getByTestId('session-comment').fill('Комментарий через полночь');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await closeDetails(page);await page.locator('#view-day').fill('2026-09-29');assert.equal(await page.getByTestId('task-row').count(),1);assert.match(await page.locator('#day-total').textContent(),/01:00:00/);await page.getByRole('button',{name:'Отчёт дня',exact:true}).click();assert.match(await page.locator('#report-text').inputValue(),/Готово <script>bad<\/script>/);await page.locator('#report-extended').check();assert.match(await page.locator('#report-text').inputValue(),/Комментарий через полночь/);await context.grantPermissions(['clipboard-read','clipboard-write']);await page.getByRole('button',{name:'Копировать',exact:true}).click();await page.getByText('Отчёт скопирован.',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),await page.locator('#report-text').inputValue());await page.evaluate(()=>window.print=()=>{window.printInvoked=true;});await page.getByRole('button',{name:'Печать / PDF',exact:true}).click();assert.equal(await page.locator('#report-print').textContent(),await page.locator('#report-text').inputValue());assert.equal(await page.locator('#report-print script,#report-print img').count(),0);const download=page.waitForEvent('download');await page.getByRole('button',{name:'Скачать',exact:true}).click();assert.equal((await download).suggestedFilename(),'tasktimer-report-2026-09-29.txt');await page.locator('#report-dialog .close-dialog').click();await page.locator('#view-day').fill('2026-09-30');assert.equal(await page.getByTestId('task-row').count(),0);}finally{await context.close();}});
test('explicit priority four and plan survive synchronized projection',async()=>{const {context,page}=await setup();try{await create(page,'План четыре');await closeDetails(page);await page.locator('[data-select-task]').check();await page.getByRole('button',{name:'Назначить приоритет 4',exact:true}).click();const result=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const{localDay}=await import('/desktop-domain.mjs');const r=await openRepository();try{const before=(await r.read()).tasks[0];await r.enableSync();const b=await r.exportBackup();await r.mergeSync(b.syncDocument);const after=(await r.read()).tasks.find(t=>t.id===before.id);return{before,after,day:localDay()};}finally{r.close();}});assert.equal(result.after.daily_priorities[result.day],4);assert.deepEqual(result.after.planned_days,result.before.planned_days);await page.getByRole('button',{name:'Из плана',exact:true}).click();await page.getByTestId('task-row').waitFor({state:'detached'});assert.equal(await page.getByTestId('task-row').count(),0);await page.getByRole('button',{name:'В работе',exact:true}).click();await page.getByRole('button',{name:'В план',exact:true}).click();await page.getByRole('button',{name:'Из плана',exact:true}).waitFor();await page.getByRole('button',{name:'Сегодня',exact:true}).click();assert.equal(await page.getByTestId('task-row').count(),1);}finally{await context.close();}});

test('legacy standalone focus still expires through unresolved remote sessions',async()=>{const {context,page}=await setup();try{const result=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const p=await import('/sync-protocol.mjs');const r=await openRepository();try{await r.dispatch({type:'createTask',values:{title:'Legacy conflict'}});await r.enableSync();const backup=await r.exportBackup(),now=new Date().toISOString();let remote=backup.syncDocument;for(const sid of ['a','b'])remote=p.changeEntity(remote,'actor-'+sid,['session',backup.tasks[0].id,sid],{interval:{started_at:now,ended_at:null},comment:''});await r.mergeSync(remote);const before=await r.exportBackup();const focus={taskId:null,started_at:now,ends_at:new Date(Date.parse(now)+60000).toISOString()};await r.dispatch({type:'replaceState',values:{...before,focus}});return{before:await r.exportBackup(),deadline:focus.ends_at};}finally{r.close();}});await page.clock.install({time:new Date(Date.parse(result.deadline)+1000)});await reload(page);await page.getByTestId('start-focus').waitFor();const after=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{return await r.exportBackup();}finally{r.close();}});assert.equal(after.focus,null);assert.deepEqual(after.tasks,result.before.tasks);assert.deepEqual(after.syncDocument,result.before.syncDocument);}finally{await context.close();}});

test('midnight closes focus accounting but preserves countdown through reload and sync until deadline',async()=>{const {context,page}=await setup();try{
 await page.clock.install({time:new Date('2026-10-05T23:59:00+03:00')});await create(page,'До полуночи');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();await page.getByRole('button',{name:'5 мин',exact:true}).click();await page.locator('#focus-panel-start').click();await page.locator('#focus-panel-stop').waitFor();const initial=await read(page);const focusId=initial.focus.taskId,previousId=initial.focus.previousTaskId,deadline=initial.focus.ends_at;
 await page.clock.setSystemTime(new Date('2026-10-06T00:01:00+03:00'));await reload(page);await page.locator('#focus-panel-stop').waitFor({timeout:3000});const midnight=await read(page);assert.equal(midnight.focus.taskId,focusId);assert.equal(midnight.focus.ends_at,deadline);const task=midnight.tasks.find(t=>t.id===focusId);assert.equal(task.status,'paused');assert.equal(task.sessions[0].ended_at,'2026-10-05T20:59:59.000Z');assert.equal(await page.locator('#focus-resume').isVisible(),false);assert.equal(await page.locator(`[data-id="${focusId}"][data-action="startTask"]`).count(),0);
 await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{await r.enableSync();const b=await r.exportBackup();await r.mergeSync(b.syncDocument);}finally{r.close();}});assert.equal((await read(page)).focus.taskId,focusId);
 await page.clock.setSystemTime(new Date(Date.parse(deadline)+1000));await reload(page);await page.locator('#focus-resume').waitFor();const ended=await read(page);assert.equal(ended.focus,null);assert.equal(ended.focusResumeTaskId,previousId);assert.equal(ended.tasks.find(t=>t.id===focusId).status,'completed');assert.deepEqual(ended.tasks.find(t=>t.id===focusId).sessions,task.sessions);
 }finally{await context.close();}});

test('day report switches Markdown and table in one dialog, preserves totals and prints selected view',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Отчёт <img src=x>');await page.getByTestId('add-session').click();await page.getByTestId('session-start').fill('2026-09-29T23:30');await page.getByTestId('session-end').fill('2026-09-30T00:30');await page.getByTestId('session-comment').fill('Комментарий <script>bad</script>');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await closeDetails(page);await page.locator('#view-day').fill('2026-09-29');await page.getByRole('button',{name:'Отчёт дня',exact:true}).click();
 const markdown=await page.locator('#report-text').inputValue();assert.equal(await page.getByRole('button',{name:'Markdown',exact:true}).getAttribute('aria-pressed'),'true');await page.getByRole('button',{name:'Таблица',exact:true}).click();assert.equal(await page.locator('#report-text').isVisible(),false);assert.match(await page.locator('#report-table').textContent(),/01:00/);assert.match(await page.locator('#report-table').textContent(),/Отчёт <img src=x>/);assert.doesNotMatch(await page.locator('#report-table').textContent(),/Комментарий/);await page.locator('#report-extended').check();assert.match(await page.locator('#report-table').textContent(),/Комментарий <script>bad<\/script>/);assert.equal(await page.locator('#report-table img,#report-table script').count(),0);
 await page.evaluate(()=>window.print=()=>{window.printInvoked=true;});await page.getByRole('button',{name:'Печать / PDF',exact:true}).click();assert.equal(await page.locator('#report-print table').count(),1);assert.equal(await page.locator('#report-print img,#report-print script').count(),0);assert.equal(await page.getByRole('button',{name:'Копировать Markdown',exact:true}).count(),1);await page.locator('#report-extended').uncheck();await page.getByRole('button',{name:'Markdown',exact:true}).click();assert.equal(await page.locator('#report-text').inputValue(),markdown);await page.getByRole('button',{name:'Таблица',exact:true}).click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.locator('#report-dialog .close-dialog').click();await page.getByRole('button',{name:'Отчёт дня',exact:true}).click();assert.equal(await page.locator('#report-text').isVisible(),true);
 }finally{await context.close();}
});

test('close warning follows unsaved editor fields and cancellation keeps the draft',async()=>{
 const {context,page}=await setup();try{
 const warned=()=>page.evaluate(()=>!window.dispatchEvent(new Event('beforeunload',{cancelable:true})));
 assert.equal(await warned(),false);
 await page.getByTestId('new-task').click();assert.equal(await warned(),false);
 await page.getByTestId('task-title').fill('Черновик');assert.equal(await warned(),true);
 const dialogEvent=page.waitForEvent('dialog',{timeout:3000});await page.evaluate(()=>setTimeout(()=>location.reload(),0));const dialog=await dialogEvent;assert.equal(dialog.type(),'beforeunload');await dialog.dismiss();
assert.equal(await page.getByTestId('task-title').inputValue(),'Черновик');assert.equal((await read(page)).tasks.length,0);
 await page.getByTestId('task-title').fill('');assert.equal(await warned(),false);
 await page.locator('[name=keep_priority]').check();assert.equal(await warned(),true);await page.locator('[name=keep_priority]').uncheck();assert.equal(await warned(),false);
 await page.locator('[name=priority]').selectOption('2');assert.equal(await warned(),true);await page.locator('[name=priority]').selectOption('4');assert.equal(await warned(),false);
 await page.getByTestId('task-title').fill('Сохранено');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});assert.equal(await warned(),false);
 await page.locator('[data-action=editTask]').first().click();assert.equal(await warned(),false);await page.locator('textarea[name=description]').fill('Отменено');assert.equal(await warned(),true);await page.locator('#editor-dialog .close-dialog').first().click();assert.equal(await warned(),false);
 }finally{await context.close();}
});

test('close warning sees timers outside filters and concentration after midnight accounting ends',async()=>{
 const{context,page}=await setup();try{
 const warned=()=>page.evaluate(()=>!window.dispatchEvent(new Event('beforeunload',{cancelable:true})));
 await create(page,'Таймер');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();assert.equal(await warned(),true);
 await page.locator('#search').fill('ничего');assert.equal(await page.getByTestId('task-row').count(),0);assert.equal(await warned(),true);
 await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).click();await page.getByRole('button',{name:'▶ Продолжить',exact:true}).waitFor();assert.equal(await warned(),false);
 await page.locator('#search').fill('');await page.clock.install({time:new Date('2026-10-05T23:59:58+03:00')});await page.locator('#focus-panel-start').click();await page.locator('#focus-panel-stop').waitFor();assert.equal(await warned(),true);
 await page.clock.runFor(3000);await page.waitForFunction(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{const s=await r.read();return s.focus&&s.tasks.every(t=>t.status!=='running');}finally{r.close();}});assert.equal(await warned(),true);
 const before=await read(page);await page.locator('#focus-panel-stop').click();await page.locator('#focus-panel-start').waitFor();assert.equal(await warned(),false);assert.ok(before.focus);
 }finally{await context.close();}
});

test('close warning protects voice startup recording recognition and unadded text but not model management',async()=>{
 const voiceMock=`export const VOICE_BYTES=100;export async function voiceReady(){return true;}export async function installVoice(){}export async function removeVoice(){}export class VoiceDictation{start(){return new Promise(r=>window.startVoice=r);}stop(){return new Promise(r=>window.finishVoice=r);}cancel(){}}`;
 const{context,page}=await setup({voiceMock});try{
 const warned=()=>page.evaluate(()=>!window.dispatchEvent(new Event('beforeunload',{cancelable:true})));
 await page.getByTestId('new-task').click();await page.getByRole('button',{name:'Диктовать: название',exact:true}).click();await page.locator('#voice-record').waitFor();assert.equal(await warned(),false);
 await page.locator('#voice-record').click();assert.equal(await warned(),true);await page.evaluate(()=>window.startVoice());await page.locator('#voice-stop').waitFor();assert.equal(await warned(),true);
 await page.locator('#voice-stop').click();assert.equal(await warned(),true);await page.evaluate(()=>window.finishVoice('Черновик голосом'));await page.locator('#voice-add:enabled').waitFor();assert.equal(await warned(),true);
 await page.locator('#voice-result').fill('');assert.equal(await warned(),false);await page.locator('#voice-result').fill('Черновик');await page.locator('#voice-add').click();await page.locator('#voice-dialog').waitFor({state:'hidden'});assert.equal(await warned(),true);
 await page.locator('#editor-dialog .close-dialog').first().click();assert.equal(await warned(),false);
 await page.getByTestId('new-task').click();await page.getByRole('button',{name:'Диктовать: название',exact:true}).click();await page.locator('#voice-record').click();await page.locator('#voice-cancel').click();await page.locator('#voice-dialog').waitFor({state:'hidden'});assert.equal(await warned(),false);
 await page.locator('#editor-dialog .close-dialog').first().click();await page.locator('#settings-button').click();await page.locator('#voice-settings').click();await page.locator('#voice-dialog').waitFor();assert.equal(await warned(),false);
 }finally{await context.close();}
});
test('new task offers add and add-start, Enter only adds, switching persists and edit keeps Save',async()=>{const {context,page}=await setup();try{
 await page.getByTestId('new-task').click();const editor=page.locator('#editor-dialog');
 assert.equal(await editor.getByRole('button',{name:'Добавить',exact:true}).count(),1);assert.equal(await editor.getByRole('button',{name:'Добавить и начать',exact:true}).count(),1);
 await page.getByTestId('task-title').fill('Only added');await page.getByTestId('task-title').press('Enter');await editor.waitFor({state:'hidden'});let state=await read(page);assert.equal(state.tasks.length,1);assert.equal(state.tasks[0].status,'open');assert.equal(state.tasks[0].sessions.length,0);
 await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('   ');await editor.getByRole('button',{name:'Добавить и начать',exact:true}).click();await page.locator('#editor-error').waitFor();assert.equal(await page.getByTestId('task-title').inputValue(),'   ');assert.equal((await read(page)).tasks.length,1);await page.getByTestId('task-title').fill('First running');await page.evaluate(()=>{const form=document.querySelector('#editor-form'),button=document.querySelector('#editor-add-start');form.requestSubmit(button);form.requestSubmit(button);});await editor.waitFor({state:'hidden'});
 await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill('Next running');const bounds=await editor.getByRole('button',{name:'Добавить и начать',exact:true}).boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390);
 await editor.getByRole('button',{name:'Добавить и начать',exact:true}).click();await editor.waitFor({state:'hidden'});state=await read(page);assert.equal(state.tasks.length,3);assert.equal(state.tasks[1].status,'paused');assert.ok(state.tasks[1].sessions[0].ended_at);assert.equal(state.tasks[2].status,'running');assert.equal(state.tasks[2].sessions.length,1);
 await reload(page);assert.deepEqual((await read(page)).tasks,state.tasks);
 await page.locator(`[data-action="editTask"][data-id="${state.tasks[2].id}"]`).click();assert.equal(await editor.getByRole('button',{name:'Сохранить',exact:true}).count(),1);assert.equal(await editor.getByRole('button',{name:'Добавить и начать',exact:true}).isVisible(),false);
 }finally{await context.close();}});
test('reminder is armed only by a visible question, continues and auto-stops at persisted deadline',async()=>{
 const {context,page}=await setup();try{
 await page.clock.install({time:new Date('2026-10-06T09:00:00Z')});
 await page.getByRole('button',{name:'Настройки и резервные копии'}).click();
 await page.locator('#reminder-minutes').fill('1');await page.locator('#reminder-save').click();await page.locator('#reminder-settings-status').filter({hasText:'Сохранено'}).waitFor();
 await page.locator('#settings-dialog .close-dialog').click();await create(page,'Продолжение');await closeDetails(page);await page.getByTestId('task-toggle').click();
 await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();await page.bringToFront();await page.clock.fastForward(61000);await page.locator('#reminder-dialog').waitFor({timeout:4000});
 await page.waitForFunction(()=>document.querySelector('#reminder-continue').disabled===false);
 let s=await read(page);assert.ok(s.reminder.pending.shownAt);assert.equal(Date.parse(s.reminder.pending.deadline)-Date.parse(s.reminder.pending.shownAt),300000);
 await page.locator('#reminder-continue').click();await page.locator('#reminder-dialog').waitFor({state:'hidden'});s=await read(page);assert.equal(s.reminder.pending.deadline,null);
 await page.clock.fastForward(61000);await page.locator('#reminder-dialog').waitFor();await page.waitForFunction(()=>!document.querySelector('#reminder-continue').disabled);s=await read(page);const deadline=s.reminder.pending.deadline;
 await reload(page);await page.locator('#reminder-dialog').waitFor();assert.equal((await read(page)).reminder.pending.deadline,deadline);
 await page.clock.fastForward(301000);await page.locator('#reminder-dialog').waitFor({state:'hidden'});s=await read(page);assert.equal(s.tasks[0].status,'paused');assert.equal(s.tasks[0].sessions[0].ended_at,deadline);
 }finally{await context.close();}
});
test('hidden reminder has no deadline and two repository clients serialize stale answers',async()=>{
 const {context,page}=await setup();try{
 await page.clock.install({time:new Date('2026-10-06T09:00:00Z')});await create(page,'В фоне');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();
 await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
 await page.clock.fastForward(45*60000);let s=await read(page);assert.equal(s.tasks[0].status,'running');assert.equal(s.reminder.pending.deadline,null);assert.equal(await page.locator('#reminder-dialog').isVisible(),false);
 await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'));});await page.locator('#reminder-dialog').waitFor();await page.waitForFunction(()=>!document.querySelector('#reminder-continue').disabled);
 const result=await page.evaluate(async()=>{
 const {openRepository}=await import('/repository.mjs');const a=await openRepository(),b=await openRepository();try{const s=await a.read(),expected=s.reminder.pending;
 await a.dispatch({type:'reminder',values:{action:'continue',expected}});await b.dispatch({type:'reminder',values:{action:'stop',expected}});return await a.read();}finally{a.close();b.close();}});
 assert.equal(result.tasks[0].status,'running');assert.equal(result.reminder.pending.deadline,null);await page.locator('#reminder-dialog').waitFor({state:'hidden'});
 }finally{await context.close();}
});

test('priority lock toggles from list by keyboard, persists and agrees with editor without changing time or priority',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Проверка приоритета');await closeDetails(page);
 const row=page.getByTestId('task-row'),lock=row.getByRole('button',{name:'Сохранять приоритет на следующий день: Проверка приоритета',exact:true});
 assert.equal(await lock.count(),1);assert.equal(await lock.getAttribute('aria-pressed'),'false');
 await row.getByRole('button',{name:'Изменить',exact:true}).click();await page.locator('[name=priority]').selectOption('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 await row.getByTestId('task-toggle').click();await row.getByRole('button',{name:'Приостановить: Проверка приоритета',exact:true}).click();await row.getByRole('button',{name:'Запустить: Проверка приоритета',exact:true}).waitFor();
 const before=(await read(page)).tasks[0];await lock.focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelector('.priority-lock')?.getAttribute('aria-pressed')==='true'&&!document.querySelector('.priority-lock').disabled);
 assert.equal(await lock.evaluate(el=>document.activeElement===el),true);
 const after=(await read(page)).tasks[0];for(const field of ['priority','daily_priorities','planned_days','sessions','status'])assert.deepEqual(after[field],before[field]);
 assert.equal(await page.locator('#details-dialog').isVisible(),false);
 await row.getByRole('button',{name:'Изменить',exact:true}).click();assert.equal(await page.locator('[name=keep_priority]').isChecked(),true);await page.locator('#editor-dialog .close-dialog').first().click();
 await reload(page);await lock.waitFor();assert.equal(await lock.getAttribute('aria-pressed'),'true');
 const bounds=await lock.boundingBox();assert.ok(bounds.width>=32&&bounds.height>=32);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 const output=path.resolve(__dirname,'../../../documents/pwa-priority-lock');await fs.mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});await page.setViewportSize({width:1440,height:900});await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
 await lock.focus();await page.keyboard.press('Space');await page.waitForFunction(()=>document.querySelector('.priority-lock')?.getAttribute('aria-pressed')==='false'&&!document.querySelector('.priority-lock').disabled);
 assert.equal((await read(page)).tasks[0].keep_priority,false);assert.equal(await lock.evaluate(el=>document.activeElement===el),true);
 await row.getByRole('button',{name:'Изменить',exact:true}).click();assert.equal(await page.locator('[name=keep_priority]').isChecked(),false);
 }finally{await context.close();}
});

test('completed task has a disabled open priority lock and disabled unchecked editor option',async()=>{
 const {context,page}=await setup();try{
 await create(page,'Завершить с замочком');await closeDetails(page);
 const row=page.getByTestId('task-row'),lock=row.locator('.priority-lock');
 await lock.click();await page.waitForFunction(()=>document.querySelector('.priority-lock').getAttribute('aria-pressed')==='true');
 await row.getByRole('button',{name:'Завершить',exact:true}).click();await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 await page.getByRole('button',{name:'Все',exact:true}).click();await lock.waitFor();assert.equal(await lock.isDisabled(),true);assert.equal(await lock.getAttribute('aria-pressed'),'false');assert.equal((await read(page)).tasks[0].keep_priority,false);
 await row.getByRole('button',{name:'Изменить',exact:true}).click();assert.equal(await page.locator('[name=keep_priority]').isDisabled(),true);assert.equal(await page.locator('[name=keep_priority]').isChecked(),false);await page.locator('#editor-dialog .close-dialog').first().click();
 await reload(page);await page.getByRole('button',{name:'Все',exact:true}).click();await lock.waitFor();assert.equal(await lock.isDisabled(),true);assert.equal(await lock.getAttribute('aria-pressed'),'false');
 }finally{await context.close();}
});

test('removing from plan preserves visible priority only when retention is enabled',async()=>{
 const {context,page}=await setup();try{
 for(const keep of [true,false]){
 await page.getByTestId('new-task').click();await page.getByTestId('task-title').fill(keep?'Сохранить один':'Сбросить один');await page.locator('[name=priority]').selectOption('1');await page.locator('[name=keep_priority]').setChecked(keep);await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 const row=page.getByTestId('task-row').filter({hasText:keep?'Сохранить один':'Сбросить один'});
 await row.getByRole('button',{name:'Из плана',exact:true}).click();await row.waitFor({state:'detached'});await page.getByRole('button',{name:'В работе',exact:true}).click();await row.waitFor();assert.equal(await row.locator('.priority-badge').innerText(),keep?'1':'4');
 await reload(page);await page.getByRole('button',{name:'В работе',exact:true}).click();await row.waitFor();assert.equal(await row.locator('.priority-badge').innerText(),keep?'1':'4');
 }
 }finally{await context.close();}
});

test('manual task order supports pointer and keyboard, reload, filters and running task pin',async()=>{
 const {context,page}=await setup();try{
 await page.setViewportSize({width:1280,height:1000});
 for(const title of ['Первый','Второй','Третий']){await create(page,title);await closeDetails(page);}
 const rows=page.getByTestId('task-row'),names=()=>rows.locator('.task-name').allTextContents();
 const before=await names();const from=rows.last().locator('.task-drag-handle'),to=rows.first();
 const a=await from.boundingBox(),b=await to.boundingBox();await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+100,b.y+5,{steps:8});await page.mouse.up();
 await page.waitForFunction(name=>document.querySelector('.task-name')?.textContent===name,before[2]);assert.deepEqual(await names(),[before[2],before[0],before[1]]);
 await reload(page);await rows.first().waitFor();assert.deepEqual(await names(),[before[2],before[0],before[1]]);
 await rows.first().locator('.task-drag-handle').focus();await page.keyboard.press('ArrowDown');await page.waitForFunction(name=>document.querySelector('.task-name')?.textContent===name,before[0]);assert.deepEqual(await names(),[before[0],before[2],before[1]]);
 const last=rows.filter({hasText:before[1]});await last.getByTestId('task-toggle').click();await page.waitForFunction(name=>document.querySelector('.task-name')?.textContent===name,before[1]);assert.equal(await rows.first().locator('.task-drag-handle').isDisabled(),true);
 await rows.first().getByTestId('task-toggle').click();await page.waitForFunction(name=>document.querySelector('.task-name')?.textContent===name,before[0]);assert.deepEqual(await names(),[before[0],before[2],before[1]]);
 await page.getByRole('button',{name:'Все',exact:true}).click();assert.deepEqual(await names(),[before[0],before[2],before[1]]);
 const sync=await page.evaluate(async()=>{const{openRepository}=await import('/repository.mjs');const r=await openRepository();try{const before=(await r.read()).taskOrder;await r.enableSync();const backup=await r.exportBackup();await r.mergeSync(backup.syncDocument);return {before,after:(await r.read()).taskOrder,backup:backup.taskOrder};}finally{r.close();}});assert.deepEqual(sync.after,sync.before);assert.deepEqual(sync.backup,sync.before);

 }finally{await context.close();}
});

test('touch drag reorders on mobile and pointer cancellation leaves order unchanged',async()=>{
 const {context,page}=await setup();try{
 for(const title of ['Мобильная первая','Мобильная вторая']){await create(page,title);await closeDetails(page);}
 const rows=page.getByTestId('task-row');await rows.first().evaluate(el=>el.scrollIntoView({block:'start'}));
 const before=await rows.locator('.task-name').allTextContents();const a=await rows.last().locator('.task-drag-handle').boundingBox(),b=await rows.first().boundingBox();
 const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:a.x+a.width/2,y:a.y+a.height/2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:b.x+100,y:b.y+10}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.waitForFunction(name=>document.querySelector('.task-name')?.textContent===name,before[1]);assert.deepEqual(await rows.locator('.task-name').allTextContents(),[before[1],before[0]]);
 await rows.first().evaluate(el=>el.scrollIntoView({block:'start'}));const x=await rows.last().locator('.task-drag-handle').boundingBox(),y=await rows.first().boundingBox();
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x.x+10,y:x.y+15}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:y.x+100,y:y.y+10}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]});
 assert.deepEqual(await rows.locator('.task-name').allTextContents(),[before[1],before[0]]);assert.equal(await page.locator('.drop-before,.drop-after,.dragging').count(),0);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 const output=path.resolve(__dirname,'../../../documents/pwa-task-order');await fs.mkdir(output,{recursive:true});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
 }finally{await context.close();}
});

test('selection clears on priority success and view switches but survives save failure',async()=>{
 const {context,page}=await setup();try{
 for(const title of ['Выбранная первая','Выбранная вторая']){await create(page,title);await closeDetails(page);}
 const checks=page.locator('[data-select-task]');await checks.nth(0).check();await checks.nth(1).check();
 await page.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){IDBObjectStore.prototype.put=original;throw new DOMException('Нет места','QuotaExceededError');};});
 await page.getByRole('button',{name:'Назначить приоритет 1',exact:true}).click();await page.locator('#global-error').waitFor({state:'visible'});assert.equal(await page.locator('[data-select-task]:checked').count(),2);
 await page.getByRole('button',{name:'Назначить приоритет 1',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#selection-count').textContent==='Выбрано: 0');assert.equal(await page.locator('[data-select-task]:checked').count(),0);assert.equal(await page.getByRole('button',{name:'Назначить приоритет 2',exact:true}).isDisabled(),true);assert.deepEqual((await read(page)).tasks.map(t=>t.priority),[1,1]);
 for(const view of ['В работе','Все','Сегодня']){await checks.first().check();await page.getByRole('button',{name:view,exact:true}).click();assert.equal(await page.locator('[data-select-task]:checked').count(),0);assert.equal(await page.locator('#selection-count').innerText(),'Выбрано: 0');assert.equal(await page.getByRole('button',{name:'Назначить приоритет 2',exact:true}).isDisabled(),true);}
 }finally{await context.close();}
});

test('background reminder attracts attention once without arming grace and clears after answer',async()=>{
 const {context,page}=await setup();try{
 const base=await page.title();await page.clock.install({time:new Date('2026-10-07T09:00:00Z')});
 await page.evaluate(()=>{window.notices=[];window.badges=[];window.closedNotices=0;Object.defineProperty(window,'Notification',{configurable:true,value:{permission:'granted'}});navigator.serviceWorker.getRegistration=async()=>({showNotification:async(title,options)=>notices.push({title,options}),getNotifications:async()=>[{close:()=>closedNotices++}]});navigator.setAppBadge=async()=>badges.push('set');navigator.clearAppBadge=async()=>badges.push('clear');});
 await create(page,'Фоновое напоминание');await closeDetails(page);await page.getByTestId('task-toggle').click();await page.getByRole('button',{name:'Ⅱ Пауза',exact:true}).waitFor();
 await page.evaluate(()=>Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'}));await page.clock.fastForward(41*60000);await page.waitForFunction(()=>window.notices.length===1);assert.match(await page.title(),/Продолжаете работать/);assert.equal(await page.locator('.brand-name').evaluate(el=>getComputedStyle(el).animationName),'brand-attention');assert.equal(await page.locator('.brand-icon').evaluate(el=>getComputedStyle(el).animationName),'none');assert.equal((await read(page)).reminder.pending.deadline,null);assert.equal(await page.locator('#reminder-dialog').isVisible(),false);
 await page.clock.fastForward(1600);assert.equal(await page.title(),base);await page.clock.fastForward(1600);assert.match(await page.title(),/Продолжаете работать/);assert.equal(await page.evaluate(()=>notices.length),1);assert.equal((await read(page)).tasks[0].status,'running');
 await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'));});await page.bringToFront();await page.clock.runFor(100);await page.locator('#reminder-dialog').waitFor();await page.waitForFunction(()=>!document.querySelector('#reminder-continue').disabled);assert.ok((await read(page)).reminder.pending.deadline);
 await page.locator('#reminder-continue').click();await page.locator('#reminder-dialog').waitFor({state:'hidden'});assert.equal(await page.title(),base);await page.waitForFunction(()=>badges.at(-1)==='clear'&&closedNotices>0);assert.equal(await page.locator('.brand-name').evaluate(el=>getComputedStyle(el).animationName),'none');assert.equal((await read(page)).tasks[0].status,'running');
 }finally{await context.close();}
});

test('focus attention survives denied notifications and clears on user interaction',async()=>{
 const {context,page}=await setup();try{
 const base=await page.title();await page.clock.install({time:new Date('2026-10-07T09:00:00Z')});await page.evaluate(()=>{Object.defineProperty(window,'Notification',{configurable:true,value:{permission:'denied'}});navigator.setAppBadge=async()=>{throw new Error('Unavailable');};navigator.clearAppBadge=async()=>{throw new Error('Unavailable');};});
 await page.getByTestId('start-focus').click();await page.getByTestId('focus-minutes').fill('1');await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});
 await page.clock.fastForward(61000);await page.waitForFunction(()=>document.title.includes('Концентрация завершена'));assert.equal(await page.locator('.brand-name').evaluate(el=>getComputedStyle(el).animationName),'brand-attention');await page.emulateMedia({reducedMotion:'reduce'});assert.deepEqual(await page.locator('.brand-name').evaluate(el=>({animation:getComputedStyle(el).animationName,color:getComputedStyle(el).color})),{animation:'none',color:'rgb(169, 98, 11)'});assert.equal((await read(page)).focus,null);assert.equal(await page.locator('#global-error').isVisible(),false);
 await page.getByRole('button',{name:'Все',exact:true}).click();assert.equal(await page.title(),base);assert.equal(await page.locator('.brand-name').evaluate(el=>el.classList.contains('needs-attention')),false);
 }finally{await context.close();}
});

test('completing tasks moves them below manual order in completion chronology and survives reload',async()=>{
 const {context,page}=await setup();try{
 for(const title of ['Первая','Вторая','Третья']){await create(page,title);await closeDetails(page);}
 const rows=page.getByTestId('task-row'),names=()=>rows.locator('.task-name').allTextContents();
 await rows.filter({hasText:'Третья'}).locator('.task-drag-handle').focus();await page.keyboard.press('ArrowUp');await page.waitForFunction(()=>document.querySelectorAll('.task-name')[1]?.textContent==='Третья');
 for(const title of ['Третья','Первая']){await rows.filter({hasText:title}).getByRole('button',{name:'Завершить',exact:true}).click();await page.getByTestId('save').click();await page.locator('#editor-dialog').waitFor({state:'hidden'});await page.waitForFunction(name=>[...document.querySelectorAll('.task-name')].at(-1)?.textContent===name,title);assert.equal(await rows.last().locator('.task-drag-handle').isDisabled(),true);}
 assert.deepEqual(await names(),['Вторая','Третья','Первая']);await reload(page);await rows.first().waitFor();assert.deepEqual(await names(),['Вторая','Третья','Первая']);await page.getByRole('button',{name:'Все',exact:true}).click();assert.deepEqual(await names(),['Вторая','Третья','Первая']);
 }finally{await context.close();}
});


test('WebDAV form previews desktop-compatible path and validates before requests',async()=>{
 const {context,page}=await setup();try{
 await page.getByRole('button',{name:'Настройки и резервные копии'}).click();
 await page.evaluate(()=>{window.davRequests=[];const original=window.fetch;window.fetch=(url,options)=>{if(String(url).startsWith('https://webdav.cloudbeeline.ru')){window.davRequests.push({url:String(url),method:options.method});return Promise.reject(new TypeError('test network failure'));}return original(url,options);};});
 const server=page.locator('#sync-form [name=url]'),path=page.locator('#sync-form [name=filePath]');
 await server.fill('https://webdav.cloudbeeline.ru');await page.locator('#sync-submit').click();
 await page.locator('#sync-error').waitFor({state:'visible'});assert.deepEqual(await page.evaluate(()=>window.davRequests),[]);
 await path.fill('tasktimer/data.json');
 const target='https://webdav.cloudbeeline.ru/tasktimer/data.json.v2.json';
 assert.equal(await page.locator('#sync-target').textContent(),'Файл синхронизации: '+target);
 await page.locator('#sync-submit').click();await page.getByText('Синхронизация не завершена.',{exact:true}).waitFor();
 await page.waitForFunction(()=>window.davRequests.length===1);
 assert.match(await page.locator('#sync-error').textContent(),/OPTIONS без авторизации/);
 await path.fill('');await server.fill('https://webdav.cloudbeeline.ru/tasktimer/data.json');
 assert.equal(await page.locator('#sync-target').textContent(),'Файл синхронизации: '+target);
 await page.locator('#sync-submit').click();await page.waitForFunction(()=>window.davRequests.length===2);
 assert.deepEqual(await page.evaluate(()=>window.davRequests),[{url:target,method:'GET'},{url:target,method:'GET'}]);
 assert.equal((await read(page)).tasks.length,0);
 }finally{await context.close();}
});
