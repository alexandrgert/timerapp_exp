import {installVoiceInterface,addVoiceButtons} from './voice-ui.mjs';
import { createWebDavClient } from './webdav-client.mjs';
import { synchronize } from './sync-controller.mjs';
import { remoteV2Path } from './sync-protocol.mjs';
import { openRepository } from './repository.mjs';
import { validateBackup, totalSeconds, sessionSeconds } from './model.mjs';
const $ = (s, root = document) => root.querySelector(s);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = seconds => { const n = Math.max(0, Math.floor(seconds || 0)); return `${String(Math.floor(n / 3600)).padStart(2,'0')}:${String(Math.floor(n / 60) % 60).padStart(2,'0')}:${String(n % 60).padStart(2,'0')}`; };
const localDate = (value = new Date()) => { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const localInput = value => { if (!value) return ''; const d = new Date(value); return `${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}${d.getSeconds() ? ':'+String(d.getSeconds()).padStart(2,'0') : ''}`; };
const clock = value => new Date(value).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
const dateLabel = value => new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'});
let repo, state = {tasks:[],focus:null}, selected = null, filter = 'active', editorAction, confirmAction, toastTimeout, reconciling = false;
const pendingWrites = new Set();
function errorAt(selector, error) { const el = $(selector); el.textContent = error?.message || String(error || 'Не удалось выполнить действие.'); el.hidden = false; }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimeout); toastTimeout = setTimeout(() => $('#toast').hidden = true, 4500); }
function accept(next) {
  const previousFocus = state.focus;
  state = next;
  if (selected && !state.tasks.some(t => t.id === selected)) selected = null;
  if (previousFocus && !state.focus && new Date(previousFocus.ends_at).getTime() <= Date.now()) {
    toast(previousFocus.taskId===null?'Концентрация завершена. Можно сделать перерыв.':'Концентрация завершена. Время сохранено.');
    if ('Notification' in window && Notification.permission === 'granted') navigator.serviceWorker?.ready.then(registration => registration.showNotification('Концентрация завершена', {body:previousFocus.taskId===null?'Можно сделать перерыв.':'Время сохранено. Можно сделать перерыв.',tag:'focus-complete'})).catch(error => errorAt('#global-error',error));
  }
  render(); renderSync(); document.dispatchEvent(new CustomEvent('tasktimer:state',{detail:state}));
}
async function dispatch(command) { if (!repo) throw new Error('Хранилище пока недоступно. Перезагрузите страницу.'); const operation = repo.dispatch(command); pendingWrites.add(operation); let next; try { next = await operation; } finally { pendingWrites.delete(operation); } accept(next); $('#global-error').hidden = true; return next; }
function taskById(id) { const task = state.tasks.find(t => t.id === id); if (!task) throw new Error('Задача уже удалена в другой вкладке.'); return task; }
function render() {
  $('#active-count').textContent = state.tasks.filter(t => t.status !== 'completed').length;
  $('#completed-count').textContent = state.tasks.filter(t => t.status === 'completed').length;
  document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('selected',b.dataset.filter === filter); b.setAttribute('aria-pressed',String(b.dataset.filter === filter));});
  const term = $('#search').value.toLocaleLowerCase('ru');
  const tasks = state.tasks.filter(t => (filter === 'completed' ? t.status === 'completed' : t.status !== 'completed') && `${t.title} ${t.description || ''}`.toLocaleLowerCase('ru').includes(term));
  $('#task-list').innerHTML = tasks.length ? tasks.map(t => `<article class="task-row ${selected === t.id ? 'chosen' : ''}" data-testid="task-row"><button class="task-select" data-action="select" data-id="${escape(t.id)}" aria-pressed="${selected === t.id}"><span class="task-name">${escape(t.title)}</span><span class="task-meta"><i class="priority p${t.priority}" aria-hidden="true"></i><span>Приоритет ${t.priority}</span>${t.day ? `<span>${escape(dateLabel(`${t.day}T12:00:00`))}</span>` : ''}${t.status === 'running' ? '<span>В работе</span>' : ''}</span></button><span class="task-time" data-task-time="${escape(t.id)}">${duration(totalSeconds(t,new Date().toISOString()))}</span>${t.status !== 'completed' ? `<button class="task-control" data-action="${t.status === 'running' ? 'pauseTask' : 'startTask'}" data-id="${escape(t.id)}" data-testid="task-toggle" aria-label="${t.status === 'running' ? 'Приостановить' : 'Запустить'}: ${escape(t.title)}">${t.status === 'running' ? 'Ⅱ' : '▶'}</button>` : ''}</article>`).join('') : `<div class="empty">${term ? '<h2>Ничего не найдено</h2><p>Попробуйте другое название.</p>' : filter === 'completed' ? '<h2>Завершённых задач пока нет</h2><p>Здесь появятся задачи, которые вы завершите.</p>' : '<h2>С чего начнём?</h2><p>Добавьте задачу и запустите таймер.<br>Каждая сессия сохранится в истории.</p><button class="primary" data-action="create">＋ Создать первую задачу</button>'}</div>`;
  renderDetails(); renderTimer(); tick();
}
function renderDetails() {
  const t = state.tasks.find(t => t.id === selected);
  if (!t) { $('#task-details').innerHTML = '<div class="details-empty"><span class="empty-symbol" aria-hidden="true">◷</span><h2>Время в деталях</h2><p>Выберите задачу, чтобы увидеть сессии и изменить записи.</p></div>'; return; }
  $('#task-details').innerHTML = `<div class="detail-heading"><p class="eyebrow">${t.status === 'completed' ? 'Завершена' : 'История задачи'}</p><h2>${escape(t.title)}</h2>${t.description ? `<p>${escape(t.description)}</p>` : ''}<div class="detail-actions"><button class="secondary" data-action="editTask" data-id="${escape(t.id)}">Изменить</button>${t.status !== 'completed' ? `<button class="secondary" data-action="focus" data-id="${escape(t.id)}">Концентрация</button><button class="secondary" data-action="completeTask" data-id="${escape(t.id)}">Завершить</button>` : ''}<button class="danger" data-action="deleteTask" data-id="${escape(t.id)}">Удалить</button></div></div><div class="detail-total"><span>Всего по задаче</span><strong data-task-time="${escape(t.id)}">${duration(totalSeconds(t,new Date().toISOString()))}</strong></div><div class="history-heading"><h3>Сессии <span class="muted">· ${t.sessions.length}</span></h3><button class="text-button" data-action="addSession" data-id="${escape(t.id)}" data-testid="add-session">＋ Добавить</button></div><div data-testid="session-list">${t.sessions.length ? [...t.sessions].sort((a,b) => new Date(b.started_at)-new Date(a.started_at)).map(s => `<article class="session" data-testid="session"><div class="session-date">${escape(dateLabel(s.started_at))}${s.ended_at && localDate(s.started_at)!==localDate(s.ended_at) ? ` — ${escape(dateLabel(s.ended_at))}` : ''}</div><div class="session-top"><span>${clock(s.started_at)} — ${s.ended_at ? clock(s.ended_at) : 'сейчас'}</span><span class="session-duration" data-session-time="${escape(s.id)}">${duration(sessionSeconds(s,new Date().toISOString()))}</span></div>${s.comment ? `<p class="session-comment">${escape(s.comment)}</p>` : ''}${s.bitrix_record_id ? '<p class="session-date">Передана в Битрикс24</p>' : ''}<div class="session-actions"><button class="text-button" data-action="editSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Изменить</button><button class="text-button" data-action="deleteSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Удалить</button></div></article>`).join('') : '<p class="empty">Сессий пока нет.<br>Запустите таймер или добавьте запись.</p>'}</div>`;
}
function renderTimer() {
  const standalone=$('#standalone-focus');standalone.hidden=state.focus?.taskId!==null;
  if(!standalone.hidden)standalone.innerHTML='<div><p class="timer-label">Концентрация</p><p class="timer-title">Без задачи</p><p class="timer-secondary">Осталось времени</p></div><div class="timer-right"><div class="timer-value" id="focus-clock" data-testid="focus-clock"></div><button class="secondary" data-action="stopFocus">Остановить</button></div>';

  const t = state.tasks.find(t => t.status === 'running'); const el = $('#active-timer'); el.hidden = !t; if (!t) return;
  const focusing = state.focus?.taskId === t.id;
  el.innerHTML = `<div><p class="timer-label">${focusing ? 'Концентрация' : 'Сейчас в работе'}</p><p class="timer-title">${escape(t.title)}</p><p class="timer-secondary">${focusing ? 'Осталось времени' : 'Текущая сессия'}</p></div><div class="timer-right"><div class="timer-value" id="live-clock" data-testid="live-clock">00:00:00</div><button class="secondary" data-action="${focusing ? 'stopFocus' : 'pauseTask'}" data-id="${escape(t.id)}">${focusing ? 'Остановить' : 'Ⅱ Пауза'}</button></div>`;
}
function tick() {
  const now = new Date(), iso = now.toISOString(), start = new Date(now.getFullYear(),now.getMonth(),now.getDate()).getTime();
  $('#today-date').textContent = now.toLocaleDateString('ru-RU',{weekday:'long',day:'numeric',month:'long'});
  let today = 0;
  for (const t of state.tasks) for (const s of t.sessions) today += Math.max(0,Math.floor((Math.min(now.getTime(),s.ended_at ? new Date(s.ended_at).getTime() : now.getTime())-Math.max(start,new Date(s.started_at).getTime()))/1000));
  $('#day-total').textContent = `Сегодня — ${duration(today)}`;
  document.querySelectorAll('[data-task-time]').forEach(el => {const t = state.tasks.find(t => t.id === el.dataset.taskTime); if(t) el.textContent=duration(totalSeconds(t,iso));});
  document.querySelectorAll('[data-session-time]').forEach(el => {const s=state.tasks.find(t=>t.id===selected)?.sessions.find(s=>s.id===el.dataset.sessionTime);if(s)el.textContent=duration(sessionSeconds(s,iso));});
  const live = $('#live-clock'); if(live) {const t=state.tasks.find(t=>t.status==='running'),s=t?.sessions.find(s=>!s.ended_at);live.textContent=duration(state.focus && state.focus.taskId===t?.id ? (new Date(state.focus.ends_at)-now)/1000 : s ? sessionSeconds(s,iso) : 0);}
  const focusClock=$('#focus-clock');if(focusClock&&state.focus?.taskId===null)focusClock.textContent=duration((new Date(state.focus.ends_at)-now)/1000);
  if (repo && state.focus && new Date(state.focus.ends_at) <= now && !reconciling) {reconciling=true; dispatch({type:'reconcile'}).catch(e=>errorAt('#global-error',e)).finally(()=>reconciling=false);}
}
function openEditor(title, fields, action, submit='Сохранить') { $('#editor-title').textContent=title; $('#editor-fields').innerHTML=fields; $('#editor-error').hidden=true; $('#editor-overwrite').hidden=true; $('#editor-form [type=submit]').textContent=submit; editorAction=action; addVoiceButtons($('#editor-form')); $('#editor-dialog').showModal(); }
function taskEditor(id) {
  const t=id ? taskById(id) : {title:'',description:'',priority:4,day:localDate()};
  openEditor(id ? 'Изменить задачу' : 'Новая задача', `<label class="field">Название<input name="title" data-testid="task-title" required maxlength="500" value="${escape(t.title)}" autofocus autocomplete="off"></label><label class="field">Описание<textarea name="description" maxlength="20000">${escape(t.description)}</textarea></label><div class="field-grid"><label class="field">Дата<input name="day" type="date" required value="${escape(t.day)}"></label><label class="field">Приоритет<select name="priority">${[1,2,3,4].map(p=>`<option value="${p}" ${Number(t.priority)===p?'selected':''}>${p}${p===1?' — высокий':p===4?' — обычный':''}</option>`).join('')}</select></label></div>`,async (form,force=false)=>{
    const fields={title:form.get('title'),description:form.get('description'),priority:Number(form.get('priority')),day:form.get('day')};
    const values=id ? Object.fromEntries(Object.entries(fields).filter(([key,value])=>value!==t[key])) : fields;
    const expected=id&&!force?Object.fromEntries(Object.keys(values).map(key=>[key,t[key]])):undefined;
    const next=await dispatch({type:id?'updateTask':'createTask',taskId:id,values,expected});
    if(!id){selected=next.tasks.at(-1)?.id;filter='active';render();}
  });
}
function timestamp(value) { const d=new Date(value); if(!Number.isFinite(d.getTime()) || localInput(d)!==value) throw new Error('Проверьте дату и время: указанного момента нет в вашем часовом поясе.'); return d.toISOString(); }
function sessionEditor(taskId,sessionId) {
  const t=taskById(taskId),s=sessionId?t.sessions.find(s=>s.id===sessionId):null;
  if(sessionId&&!s)throw new Error('Сессия уже удалена.');
  const initialStart=localInput(s?.started_at || new Date(Date.now()-3600000)), initialEnd=localInput(s ? s.ended_at : new Date());
  openEditor(s?'Изменить сессию':'Добавить сессию',`<label class="field">Начало<input type="datetime-local" step="1" name="started_at" required value="${initialStart}" data-testid="session-start"></label><label class="field">Окончание${s&&!s.ended_at?' (пусто — таймер продолжает идти)':''}<input type="datetime-local" step="1" name="ended_at" ${s&&!s.ended_at?'':'required'} value="${initialEnd}" data-testid="session-end"></label><label class="field">Комментарий<textarea name="comment" maxlength="20000" data-testid="session-comment">${escape(s?.comment||'')}</textarea></label>${s?.bitrix_record_id?'<p class="field-note">Запись уже передана в Битрикс24. Изменение останется локальным и не будет отправлено повторно.</p>':''}`,async (form,force=false)=>{
    const start=form.get('started_at'),end=form.get('ended_at');
    const values={};
    if(!s || form.get('comment')!==s.comment) values.comment=form.get('comment');
    // Unchanged fields are omitted so another tab's interval edits are preserved.
    if(!s || start!==initialStart) values.started_at=timestamp(start);
    if(!s || end!==initialEnd) values.ended_at=end?timestamp(end):null;
    const expected=s&&!force?Object.fromEntries(Object.keys(values).map(key=>[key,s[key]])):undefined;
    await dispatch({type:s?'updateSession':'addSession',taskId,sessionId,values,expected});
  });
}
function confirm(title,message,action,{label='Удалить',backup=false}={}) { $('#confirm-title').textContent=title;$('#confirm-text').textContent=message;$('#confirm-submit').textContent=label;$('#confirm-error').hidden=true;$('#confirm-export').hidden=!backup;confirmAction=action;$('#confirm-dialog').showModal(); }
async function exportBackup() { if(!repo)throw new Error('Хранилище недоступно.'); const current=await repo.exportBackup();delete current.sync;const blob=new Blob([JSON.stringify(current,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`tasktimer-${localDate()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);toast('Резервная копия подготовлена.'); }
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.classList.contains('close-dialog')){if(!button.closest('dialog').dataset.busy)button.closest('dialog').close();return;}
  const action=button.dataset.action,id=button.dataset.id;if(!action)return;
  try {
    if(action==='select'){selected=id;renderDetails();render();return;}
    if(action==='create'){taskEditor();return;}
    if(action==='editTask'){taskEditor(id);return;}
    if(action==='addSession'||action==='editSession'){sessionEditor(id,button.dataset.session);return;}
    if(action==='deleteTask'){const t=taskById(id);confirm('Удалить задачу?',`«${t.title}» и все её сессии будут удалены. Отменить это действие нельзя.`,()=>dispatch({type:'deleteTask',taskId:id}));return;}
    if(action==='deleteSession'){confirm('Удалить сессию?','Запись и её время будут удалены из истории задачи.',()=>dispatch({type:'deleteSession',taskId:id,sessionId:button.dataset.session}));return;}
    if(action==='focus'){openEditor('Концентрация',`<label class="field">Задача<select name="taskId" data-testid="focus-task"><option value="">Без задачи</option>${state.tasks.filter(t=>t.status!=='completed').map(t=>`<option value="${escape(t.id)}" ${t.id===id?'selected':''}>${escape(t.title)}</option>`).join('')}</select></label><label class="field">Длительность, минуты<input type="number" name="minutes" min="1" max="180" step="1" value="25" required data-testid="focus-minutes"></label><p class="field-note">Без задачи время не добавляется к сессиям. В фоне сигнал не гарантирован.</p>`,form=>dispatch({type:'startFocus',taskId:form.get('taskId')||null,values:{minutes:Number(form.get('minutes'))}}),'Начать');return;}
    button.disabled=true;await dispatch({type:action,taskId:id});
  }catch(error){errorAt('#global-error',error);}finally{button.disabled=false;}
});
for(const [id,errorId,getAction] of [['editor-form','#editor-error',()=>()=>editorAction(new FormData($('#editor-form')))],['confirm-form','#confirm-error',()=>confirmAction]]) $( `#${id}`).addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,dialog=form.closest('dialog');if(dialog.dataset.busy)return;dialog.dataset.busy='true';const buttons=form.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await getAction()();dialog.close();}catch(error){errorAt(errorId,error);if(id==='editor-form')$('#editor-overwrite').hidden=error.name!=='ConcurrentEditError';}finally{delete dialog.dataset.busy;buttons.forEach(b=>b.disabled=false);}});
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(dialog.dataset.busy)event.preventDefault();}));
$('#new-task').addEventListener('click',()=>taskEditor());
$('#search').addEventListener('input',render);
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;render();}));
$('#settings-button').addEventListener('click',()=>$('#settings-dialog').showModal());
$('#export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#import-error',e)));
$('#confirm-export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#confirm-error',e)));
$('#import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>20*1024*1024)throw new Error('Файл слишком большой. Максимум 20 МБ.');const imported=validateBackup(JSON.parse(await file.text()));$('#import-error').hidden=true;confirm(imported.syncDocument?'Объединить журнал из копии?':'Заменить данные копией?',imported.syncDocument?'Журнал копии объединится с текущим. Удаления и конфликтующие варианты сохранятся для выбора.':`В копии задач: ${imported.tasks.length}. Все текущие задачи и сессии будут заменены. Сначала рекомендуем скачать текущую копию.`,async()=>{await dispatch({type:'replaceState',values:imported});selected=null;render();toast('Резервная копия восстановлена.');},{label:imported.syncDocument?'Объединить':'Заменить данные',backup:true});}catch(error){errorAt('#import-error',error);}finally{event.target.value='';}});
$('#enable-notifications').addEventListener('click',async()=>{try{if(!('Notification'in window))throw new Error('Этот браузер не поддерживает уведомления.');const permission=await Notification.requestPermission();$('#notification-status').textContent=permission==='granted'?'Уведомления разрешены.':permission==='denied'?'Уведомления запрещены в настройках браузера.':'Разрешение не выдано.';}catch(error){$('#notification-status').textContent=error.message;}});
function connection(){ $('#connection').textContent=navigator.onLine?'':'Офлайн'; }window.addEventListener('online',connection);window.addEventListener('offline',connection);connection();
try{repo=await openRepository();accept(await repo.read());repo.subscribe((next,error)=>{if(error){errorAt('#global-error',error);return;}if(next?.tasks)accept(next);else repo.read().then(accept).catch(e=>errorAt('#global-error',e));});}catch(error){errorAt('#global-error',error);$('#task-list').innerHTML='<p class="empty">Не удалось открыть локальные данные.<br>Проверьте разрешения браузера и перезагрузите страницу.</p>';}
window.addEventListener('tasktimer:before-update', event => { event.detail.waitUntil((async () => { if (!repo) throw new Error('Хранилище недоступно. Обновление отменено.'); await Promise.all([...pendingWrites]); await repo.read(); })()); });
setInterval(tick,1000);

let syncAbort=null;
function renderSync(){
 const sync=state.sync,conflicts=sync?.conflicts||[],active=sync?.activeSessions||[];
 $('#sync-attention').hidden=!(conflicts.length||sync?.projectionError);
 $('#sync-backup').hidden=!sync?.enabled;
 $('#sync-conflicts').replaceChildren();
 if(sync?.projectionError){const p=document.createElement('p');p.className='error';p.textContent='Новые данные сохранены в журнале, но пока не применены: '+sync.projectionError;$('#sync-conflicts').append(p);}
 for(const conflict of conflicts){
   const box=document.createElement('section'),title=document.createElement('p');title.textContent=`${conflict.entity.join(' / ')} — ${conflict.field==='$alive'?'Удаление или сохранение':conflict.field}: выберите вариант`;box.append(title);
   for(const candidate of conflict.candidates){const b=document.createElement('button');b.className='secondary';b.textContent=conflict.field==='$alive'?(candidate.value?'Сохранить запись':'Удалить запись'):JSON.stringify(candidate.value);b.addEventListener('click',async()=>{b.disabled=true;try{accept(await repo.resolveSync(conflict.entity,conflict.field,candidate.value,conflict.candidates));$('#sync-status').textContent='Выбор сохранён. Синхронизируйте для передачи другим устройствам.';}catch(e){errorAt('#sync-error',e);}finally{b.disabled=false;}});box.append(b);}
   $('#sync-conflicts').append(box);
 }
 if(active.length){const p=document.createElement('p');p.textContent='Одновременно запущено несколько сессий. Выберите одну: остальные завершатся текущим временем, их записи сохранятся.';$('#sync-conflicts').append(p);for(const item of active){const b=document.createElement('button');b.className='secondary';b.textContent=`Оставить: ${item.taskTitle} (${item.started_at})`;b.addEventListener('click',()=>confirm('Оставить одну активную сессию?','Остальные активные сессии завершатся текущим временем; история сохранится.',async()=>accept(await repo.keepActive(item.taskId,item.sessionId,active)),{label:'Завершить остальные'}));$('#sync-conflicts').append(b);}}
}
$('#sync-attention').addEventListener('click',()=>$('#settings-dialog').showModal());
$('#sync-form').addEventListener('submit',async event=>{
 event.preventDefault();if(syncAbort)return;const form=new FormData(event.currentTarget);syncAbort=new AbortController();$('#sync-submit').disabled=true;$('#sync-cancel').hidden=false;$('#sync-error').hidden=true;$('#sync-status').textContent='Синхронизация…';
 try{const url=new URL(form.get('url'));const options={username:form.get('username'),password:form.get('password')};const legacyClient=createWebDavClient({url:url.href,...options});url.pathname=remoteV2Path(url.pathname);const client=createWebDavClient({url:url.href,...options});const targetKey=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(url.href+'\n'+options.username))),b=>b.toString(16).padStart(2,'0')).join('');accept(await synchronize(repo,client,{signal:syncAbort.signal,legacyClient,targetKey}));$('#sync-status').textContent=state.sync?.conflicts.length||state.sync?.projectionError?'Обмен завершён; разрешите конфликты ниже.':'Синхронизация завершена.';}catch(e){if(syncAbort.signal.aborted)$('#sync-status').textContent='Обмен отменён. Уже сохранённые данные остаются на устройстве.';else{errorAt('#sync-error',e);$('#sync-status').textContent='Синхронизация не завершена.';}}finally{syncAbort=null;$('#sync-submit').disabled=false;$('#sync-cancel').hidden=true;}
});
$('#sync-cancel').addEventListener('click',()=>syncAbort?.abort());
$('#sync-backup').addEventListener('click',async()=>{try{const backup=await repo.migrationBackup();if(!backup)throw new Error('Копия до первого обмена отсутствует.');const url=URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='tasktimer-before-webdav.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){errorAt('#sync-error',e);}});

installVoiceInterface({confirmRemoval:action=>confirm('Удалить голосовую модель?','Диктовка станет недоступной до повторной загрузки. Задачи и записи сохранятся.',action)});

$('#editor-overwrite').addEventListener('click',()=>confirm('Заменить изменённые поля вашим вариантом?','Текущие значения показаны в ошибке редактора. Только изменённые вами поля будут заменены.',async()=>{await editorAction(new FormData($('#editor-form')),true);$('#editor-dialog').close();},{label:'Сохранить мой вариант'}));
