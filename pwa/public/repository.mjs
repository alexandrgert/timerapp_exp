import {initialState, apply, validateBackup} from './model.mjs';
import {importLegacy, reconcileTasks, mergeDocuments, projectTasks, resolveConflict, changeEntity, validateDocument, emptyDocument} from './sync-protocol.mjs';

function canonicalTasks(tasks){
 return tasks.map(task=>{
   const copy=structuredClone(task);delete copy.priority;
   copy.daily_priorities={...task.daily_priorities};
   if(task.priority===4)delete copy.daily_priorities[task.day];else copy.daily_priorities[task.day]=task.priority;
   return copy;
 });
}
function projectSynced(current, sync) {
 const projected=projectTasks(sync.document);
 const tasks=projected.tasks.map(task=>({...task, description:task.description??'', priority:('daily_priorities'in task)?(task.daily_priorities?.[task.day]??4):(task.priority??4), completed_at:task.completed_at??null,
   sessions:task.sessions.map(session=>({...session,comment:session.comment??'',bitrix_record_id:session.bitrix_record_id??null}))}));
 const active=tasks.flatMap(task=>task.sessions.filter(session=>session.ended_at===null).map(session=>({taskId:task.id,taskTitle:task.title,sessionId:session.id,started_at:session.started_at})));
 sync.conflicts=projected.conflicts;sync.activeSessions=active.length>1?active:[];sync.projectionError=null;
 // Status is derived for display; the causal source value remains in the log.
 for(const task of tasks){if(!['open','running','paused','completed'].includes(task.status))throw new Error('Некорректный статус задачи в синхронизации');const running=task.sessions.some(session=>session.ended_at===null);if(running)task.status='running';else if(task.status==='running')task.status='paused';}
 let focus=current.focus;
 if(focus&&focus.taskId!==null&&!tasks.some(task=>task.id===focus.taskId&&task.sessions.some(session=>session.ended_at===null)))focus=null;
 // Validate all domain fields even when multi-active projection needs explicit resolution.
 validateBackup({...current,tasks,focus:null},{allowMultipleActive:true});
 if(active.length>1){sync.projectionError='Одновременно работают несколько сессий. Выберите одну.';return current;}
 return validateBackup({...current,tasks,focus});
}
const expose=(state,sync)=>sync?{...state,sync:{enabled:true,conflicts:sync.conflicts||[],activeSessions:sync.activeSessions||[],projectionError:sync.projectionError||null}}:state;


function storageError(error) {
 if(error?.name==='QuotaExceededError')return new Error('Недостаточно места на устройстве. Освободите место и повторите; данные не сброшены.');
 if(error?.name==='VersionError')return new Error('Хранилище обновлено новой версией приложения. Обновите страницу.');
 return new Error(`Не удалось прочитать или сохранить данные: ${error?.message || 'хранилище недоступно'}`);
}

export async function openRepository({name='tasktimer-pwa'}={}) {
 if(!globalThis.indexedDB)throw new Error('Браузер не предоставляет локальное хранилище IndexedDB.');
 const db=await new Promise((resolve,reject)=>{
 let settled=false;
 const request=indexedDB.open(name,1);
 request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains('state'))request.result.createObjectStore('state');};
 request.onerror=()=>{settled=true;reject(storageError(request.error));};
 request.onblocked=()=>{settled=true;reject(new Error('Закройте другие вкладки TaskTimer и повторите открытие хранилища.'));};
 request.onsuccess=()=>{if(settled)request.result.close();else{settled=true;resolve(request.result);}};
 });
 let closed=false;
 const listeners=new Set();
 let channel=null;try{if(globalThis.BroadcastChannel)channel=new BroadcastChannel(`${name}:changes`);}catch{/* Window focus still refreshes if the browser disallows channels. */}
 const notify=(state,error=null)=>{for(const fn of listeners){try{fn(state,error);}catch(e){console.error('Ошибка обновления интерфейса TaskTimer',e);}}};
 function transaction(command, operation) {
 if(closed)return Promise.reject(new Error('Хранилище закрыто. Обновите страницу.'));
 return new Promise((resolve,reject)=>{
 let tx;try{tx=db.transaction('state','readwrite');}catch(error){reject(storageError(error));return;}
 let failure=null,result,changed=false,returned;
 tx.onabort=()=>reject(failure||storageError(tx.error));
 tx.onerror=()=>{}; // The abort event carries the final transaction outcome.
 tx.oncomplete=()=>{
 if(changed){notify(result);try{channel?.postMessage({type:'changed'});}catch{/* A closing tab must not turn a committed write into a failure. */}}
 resolve(returned??result);
 };
 const store=tx.objectStore('state');const request=store.get('current');
 request.onsuccess=()=>{
 const syncRequest=store.get('sync');
 syncRequest.onsuccess=()=>{
 try {
 const current=request.result===undefined?initialState():validateBackup(request.result);
 let sync=syncRequest.result;
 const before=JSON.stringify({current,sync});
 if(operation?.type==='enable'&&!sync){
   store.put(current,'sync-migration-backup');
   sync={actor:crypto.randomUUID(),document:importLegacy(canonicalTasks(current.tasks),crypto.randomUUID())};
 }
 if(operation?.type==='restore'){
   const restored=validateDocument(operation.values.syncDocument);
   if(!sync){store.put(current,'sync-migration-backup');sync={actor:crypto.randomUUID(),document:importLegacy(canonicalTasks(current.tasks),crypto.randomUUID())};}
   sync.actor=crypto.randomUUID();sync.document=mergeDocuments(sync.document,restored);
   if(operation.values.legacyRemoteSnapshot){const legacyTasks=operation.values.legacyRemoteSnapshot.tasks;if(!Array.isArray(legacyTasks))throw new Error('Некорректная копия старых задач');store.put({tasks:legacyTasks},'sync-legacy-remote-backup');}
 }
 let next=current;
 if(sync&&operation?.type==='legacy'&&!(sync.remoteImports||[]).includes(operation.targetKey)){
   if(operation.snapshot){
     const imported=importLegacy(operation.snapshot.tasks,crypto.randomUUID());
     sync.document=mergeDocuments(sync.document,imported);
     store.put({tasks:operation.snapshot.tasks},'sync-legacy-remote-backup');
   }
   sync.remoteImports=[...new Set([...(sync.remoteImports||[]),operation.targetKey])];
 }
 if(sync&&operation?.type==='remoteSeen')sync.remoteImports=[...new Set([...(sync.remoteImports||[]),operation.targetKey])];
 if(sync&&operation?.type==='merge'&&operation.document)sync.document=mergeDocuments(sync.document,operation.document);
 if(sync&&operation?.type==='resolve'){
   const currentConflict=projectTasks(sync.document).conflicts.find(c=>JSON.stringify(c.entity)===JSON.stringify(operation.entity)&&c.field===operation.field);
   if(!currentConflict||JSON.stringify(currentConflict.candidates)!==JSON.stringify(operation.expectedCandidates))throw new Error('Варианты конфликта изменились. Повторите выбор после обновления.');
   sync.document=resolveConflict(sync.document,sync.actor,operation.entity,operation.field,operation.value);
 }
 if(sync&&operation?.type==='keepActive'){
   const active=projectTasks(sync.document).tasks.flatMap(task=>task.sessions.filter(s=>s.ended_at===null).map(s=>({taskId:task.id,session:s})));
   const activeKeys=active.map(x=>JSON.stringify([x.taskId,x.session.id])).sort();
   if(JSON.stringify(activeKeys)!==JSON.stringify((operation.expectedActive||[]).map(x=>JSON.stringify([x.taskId,x.sessionId])).sort()))throw new Error('Список активных сессий изменился. Повторите выбор после обновления.');
   if(!active.some(x=>x.taskId===operation.taskId&&x.session.id===operation.sessionId))throw new Error('Список активных сессий изменился. Обновите его.');
   for(const item of active)if(item.taskId!==operation.taskId||item.session.id!==operation.sessionId){
     const ended=new Date().toISOString();if(Date.parse(ended)<Date.parse(item.session.started_at))throw new Error('Сессия начинается в будущем: сначала исправьте часы устройства.');
     const interval={started_at:item.session.started_at,ended_at:ended};
     if('duration_seconds'in item.session)interval.duration_seconds=Math.floor((Date.parse(ended)-Date.parse(item.session.started_at))/1000);
     sync.document=changeEntity(sync.document,sync.actor,['session',item.taskId,item.session.id],{interval});
   }
 }
 if(sync)next=projectSynced(current,sync);
 const localFocusOnly = ((!command||command.type==='reconcile'||command.type==='stopFocus')&&next.focus?.taskId===null) || (command?.type==='startFocus'&&command.taskId==null&&(!next.focus||next.focus.taskId===null));
 if(sync?.projectionError&&localFocusOnly){
   // Local standalone focus never writes task registers, including during unresolved remote starts.
   next=validateBackup(apply(next,command||{type:'reconcile'}));
 } else {
 if(sync?.projectionError&&command&&command.type!=='reconcile')throw new Error('Сначала разрешите конфликт синхронизации в настройках. '+sync.projectionError);
 if(!sync?.projectionError){
   const reconciled=sync?.conflicts?.length&&next.focus?.taskId!==null?next:apply(next,{type:'reconcile'});
   if(command?.expected){
     const task=reconciled.tasks.find(t=>t.id===command.taskId);
     const entity=command.sessionId?task?.sessions.find(s=>s.id===command.sessionId):task;
     if(!entity)throw new Error('Запись удалена на другом устройстве или в другой вкладке. Черновик сохранён в форме.');
     const changed=Object.keys(command.expected).filter(key=>JSON.stringify(entity[key])!==JSON.stringify(command.expected[key]));
     if(changed.length){const error=new Error('Эти поля изменились после открытия формы: '+changed.map(key=>key+' = '+JSON.stringify(entity[key])).join('; ')+'. Ваш черновик сохранён.');error.name='ConcurrentEditError';throw error;}
   }
   const applied=validateBackup(command?apply(reconciled,command):reconciled);
   if(sync){
     if(command?.type!=='replaceState'){
       const delta=reconcileTasks(emptyDocument(),canonicalTasks(next.tasks),canonicalTasks(applied.tasks),'change-probe');
       for(const op of delta.ops){
         if(sync.conflicts.some(c=>JSON.stringify(c.entity)===JSON.stringify(op.entity)&&Object.hasOwn(op.changes,c.field)))throw new Error('Сначала разрешите конфликт этого поля в настройках синхронизации. Черновик сохранён в форме.');
       }
     }
     if(command?.type==='replaceState')sync.actor=crypto.randomUUID();
     sync.document=reconcileTasks(sync.document,canonicalTasks(next.tasks),canonicalTasks(applied.tasks),sync.actor);
   }
   next=applied;
 }
 }
 // Public backup metadata is not local synchronization state.
 delete next.sync;
 changed=request.result===undefined||before!==JSON.stringify({current:next,sync});
 if(changed){store.put(next,'current');if(sync)store.put(sync,'sync');}
 result=expose(next,sync);
 if(operation?.type==='needsLegacy')returned=!(sync.remoteImports||[]).includes(operation.targetKey);
 if(operation?.type==='merge')returned={state:result,document:sync.document};
 if(operation?.type==='export'){
   returned=sync?{...next,syncDocument:structuredClone(sync.document)}:next;
   const legacyBackup=store.get('sync-legacy-remote-backup');legacyBackup.onsuccess=()=>{if(legacyBackup.result)returned={...returned,legacyRemoteSnapshot:legacyBackup.result};};
 }
 }catch(error){failure=error;tx.abort();}
 };
 };
 });
 }
 const refresh=()=>{if(!closed)transaction().then(s=>notify(s)).catch(e=>notify(undefined,e));};
 const onVisibility=()=>{if(globalThis.document?.visibilityState==='visible')refresh();};
 if(channel)channel.onmessage=refresh;
 globalThis.addEventListener?.('focus',refresh);
 globalThis.document?.addEventListener('visibilitychange',onVisibility);
 function close() {
 if(closed)return;closed=true;db.close();channel?.close();
 globalThis.removeEventListener?.('focus',refresh);globalThis.document?.removeEventListener('visibilitychange',onVisibility);listeners.clear();
 }
 db.onversionchange=()=>{notify(undefined,new Error('Хранилище обновляется в другой вкладке. Обновите страницу.'));close();};
 db.onclose=()=>{if(!closed){notify(undefined,new Error('Соединение с хранилищем прервано. Обновите страницу.'));close();}};
 return {
 read:()=>transaction(),
 exportBackup:()=>transaction(null,{type:'export'}),
 enableSync:()=>transaction(null,{type:'enable'}),
 importRemoteLegacy:(snapshot,targetKey='default')=>transaction(null,{type:'legacy',snapshot,targetKey}),
 needsLegacyImport:(targetKey='default')=>transaction(null,{type:'needsLegacy',targetKey}),
 markRemoteSeen:(targetKey='default')=>transaction(null,{type:'remoteSeen',targetKey}),
 mergeSync:document=>transaction(null,{type:'merge',document}),
 resolveSync:(entity,field,value,expectedCandidates)=>transaction(null,{type:'resolve',entity,field,value,expectedCandidates}),
 keepActive:(taskId,sessionId,expectedActive)=>transaction(null,{type:'keepActive',taskId,sessionId,expectedActive}),
 migrationBackup:()=>new Promise((resolve,reject)=>{const tx=db.transaction('state');const req=tx.objectStore('state').get('sync-migration-backup');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(storageError(req.error));}),
 dispatch:command=>{
 // Validate external import before opening a write transaction; validation is repeated on apply.
 try{if(command.type==='replaceState'){command={...command,values:validateBackup(command.values)};if(command.values.syncDocument){validateDocument(command.values.syncDocument);return transaction(null,{type:'restore',values:command.values});}}}catch(error){return Promise.reject(error);}
 return transaction(command);
 },
 subscribe:callback=>{listeners.add(callback);return()=>listeners.delete(callback);},
 close,
 };
}
