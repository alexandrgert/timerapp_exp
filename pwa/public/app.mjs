import {installVoiceInterface,addVoiceButtons} from './voice-ui.mjs';
import { createWebDavClient, resolveWebDavUrls } from './webdav-client.mjs';
import { synchronize } from './sync-controller.mjs';
import { openRepository } from './repository.mjs';
import { localDay, timerPanelTask, priorityFor, secondsOnDay, visibleTasks, dayReportData, formatDayReport } from './desktop-domain.mjs';
import { validateBackup, totalSeconds, sessionSeconds } from './model.mjs';
const $ = (s, root = document) => root.querySelector(s);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = seconds => { const n = Math.max(0, Math.floor(seconds || 0)); return `${String(Math.floor(n / 3600)).padStart(2,'0')}:${String(Math.floor(n / 60) % 60).padStart(2,'0')}:${String(n % 60).padStart(2,'0')}`; };
const localDate = (value = new Date()) => { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const localInput = value => { if (!value) return ''; const d = new Date(value); return `${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}${d.getSeconds() ? ':'+String(d.getSeconds()).padStart(2,'0') : ''}`; };
const clock = value => new Date(value).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
const dateLabel = value => new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'});
let repo, state = {tasks:[],focus:null}, selected = null, filter = 'today', editorAction, confirmAction, toastTimeout, reconciling = false;
const pendingWrites = new Set();
const pendingPriorityLocks = new Set();
let taskDrag=null, reorderBusy=false;
const attentionBaseTitle=document.title, attentionEvents=new Map(), attentionSeen=new Map();
let attentionInterval=null,attentionPhase=true,attentionBadge=Promise.resolve(),attentionInitialized=false;
const attentionTag=kind=>`tasktimer-attention:${location.pathname}:${kind}`;
function paintAttention(){const event=attentionEvents.get('reminder')||attentionEvents.get('focus');document.title=event&&attentionPhase?`⚠ ${event.title} — TaskTimer`:attentionBaseTitle;}
function refreshAttention(){
 $('.brand-name').classList.toggle('needs-attention',attentionEvents.size>0);
 clearInterval(attentionInterval);attentionInterval=null;attentionPhase=true;paintAttention();
 if(attentionEvents.size&&!matchMedia('(prefers-reduced-motion: reduce)').matches)attentionInterval=setInterval(()=>{attentionPhase=!attentionPhase;paintAttention();},1500);
 attentionBadge=attentionBadge.then(async()=>{try{if(attentionEvents.size)await navigator.setAppBadge?.();else await navigator.clearAppBadge?.();}catch{/* Title remains available when OS badges are unsupported. */}});
}
async function attentionNotification(kind,event){
 try{
 if(!('Notification'in window)||Notification.permission!=='granted')return;
 const registration=await navigator.serviceWorker?.getRegistration();
 if(!registration||attentionEvents.get(kind)?.key!==event.key)return;
 await registration.showNotification(event.title,{body:event.body,tag:attentionTag(kind)});
 // An answer may arrive while the OS notification is being created.
 if(!attentionEvents.has(kind))for(const n of await registration.getNotifications({tag:attentionTag(kind)}))if(!attentionEvents.has(kind))n.close();
 }catch{/* Notification restrictions must not interrupt timers or answers. */}
}
function setAttention(kind,event){
 if(attentionEvents.get(kind)?.key===event.key)return;
 attentionEvents.set(kind,event);refreshAttention();
 if(attentionSeen.get(kind)!==event.key){attentionSeen.set(kind,event.key);void attentionNotification(kind,event);}
}
function clearAttention(kind){
 if(!attentionEvents.delete(kind))return;refreshAttention();
 void(async()=>{try{const registration=await navigator.serviceWorker?.getRegistration();if(registration&&!attentionEvents.has(kind))for(const n of await registration.getNotifications({tag:attentionTag(kind)}))if(!attentionEvents.has(kind))n.close();}catch{/* Optional OS integration. */}})();
}
function syncReminderAttention(){
 if(!attentionInitialized){attentionInitialized=true;refreshAttention();}
 const p=state.reminder?.pending;
 if(p&&Date.now()>=Date.parse(p.dueAt)&&!state.sync?.projectionError&&!state.sync?.conflicts?.length&&(!p.deadline||Date.now()<Date.parse(p.deadline)))setAttention('reminder',{key:p.generation,title:'Продолжаете работать?',body:'Откройте TaskTimer, чтобы продолжить задачу или остановить таймер.'});
 else clearAttention('reminder');
}
function acknowledgeFocusAttention(){if(document.visibilityState==='visible'&&document.hasFocus())clearAttention('focus');}
window.addEventListener('focus',acknowledgeFocusAttention);
document.addEventListener('pointerdown',acknowledgeFocusAttention);
document.addEventListener('keydown',acknowledgeFocusAttention);
let reminderSettingsBaseline='';
let editorBaseline='', closeWarningAttached=false, voiceRisk='', voiceRevision=0;
function editorSnapshot(){return JSON.stringify([...$('#editor-fields').querySelectorAll('input,textarea,select')].map(el=>[el.name,el.type==='checkbox'||el.type==='radio'?el.checked:el.value]));}
function closeRisks(){
 const editor=$('#editor-dialog').open?editorSnapshot():'';
 const dirty=editor&&editor!==editorBaseline?editor:'';
 const running=state.tasks.filter(t=>t.status==='running').map(t=>[t.id,t.sessions.filter(s=>!s.ended_at).map(s=>[s.id,s.started_at])]);
 const focus=Date.parse(state.focus?.ends_at)>Date.now()?state.focus:null;
 const voice=$('#voice-dialog').open?voiceRisk:'';
 const reminderSettings=reminderSettingsDirty()?reminderSettingsSnapshot():'';
 return dirty||reminderSettings||running.length||focus||voice||pendingWrites.size?JSON.stringify({dirty,reminderSettings,running,focus,voice,voiceRevision:voice?voiceRevision:0,pending:pendingWrites.size}):'';
}
function warnBeforeClose(event){if(!closeRisks())return;event.preventDefault();event.returnValue='';}
function refreshCloseWarning(){
 const needed=!!closeRisks();if(needed===closeWarningAttached)return;
 window[needed?'addEventListener':'removeEventListener']('beforeunload',warnBeforeClose);closeWarningAttached=needed;
}
$('#editor-form').addEventListener('input',refreshCloseWarning);
$('#editor-form').addEventListener('change',refreshCloseWarning);
$('#editor-dialog').addEventListener('close',refreshCloseWarning);

let viewDay=localDate(), focusMinutes=20, lastDay=localDate();
const selectedTasks=new Set(), priorityFilters=new Set([1,2,3,4]);
$('#view-day').value=viewDay;
function errorAt(selector, error) { const el = $(selector); el.textContent = error?.message || String(error || 'Не удалось выполнить действие.'); el.hidden = false; }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimeout); toastTimeout = setTimeout(() => $('#toast').hidden = true, 4500); }
function accept(next) {
  const previousFocus = state.focus;
  const previousStop=state.reminder?.lastStopped;
  state = next;
  if(state.reminder?.lastStopped&&JSON.stringify(previousStop)!==JSON.stringify(state.reminder.lastStopped)){const stopped=state.reminder.lastStopped,key=`tasktimer:reminder-stop:${location.pathname}`,identity=JSON.stringify(stopped);let alreadySeen=false;try{alreadySeen=sessionStorage.getItem(key)===identity;sessionStorage.setItem(key,identity);}catch{/* The in-memory previousStop still prevents repeated notices this visit. */}if(!alreadySeen)toast(`Таймер задачи «${stopped.title}» остановлен без ответа на напоминание (${clock(stopped.at)}).`);}
  if (selected && !state.tasks.some(t => t.id === selected)) selected = null;
  if (previousFocus && !state.focus && new Date(previousFocus.ends_at).getTime() <= Date.now()) {
    toast(previousFocus.taskId===null?'Концентрация завершена. Можно сделать перерыв.':'Концентрация завершена. Время сохранено.');
    setAttention('focus',{key:`${previousFocus.started_at}:${previousFocus.ends_at}`,title:'Концентрация завершена',body:'Можно сделать перерыв. Откройте TaskTimer.'});
  }
  if(!$('#settings-dialog').open)loadReminderSettings();
  syncReminderAttention();refreshCloseWarning(); render(); renderSync(); document.dispatchEvent(new CustomEvent('tasktimer:state',{detail:state}));
}
async function dispatch(command) { if (!repo) throw new Error('Хранилище пока недоступно. Перезагрузите страницу.'); const operation = repo.dispatch(command); pendingWrites.add(operation); refreshCloseWarning(); let next; try { next = await operation; } finally { pendingWrites.delete(operation); refreshCloseWarning(); } accept(next); $('#global-error').hidden = true; return next; }
function taskById(id) { const task = state.tasks.find(t => t.id === id); if (!task) throw new Error('Задача уже удалена в другой вкладке.'); return task; }
function render() {
  cancelTaskDrag();
  const focusedLock=document.activeElement?.matches('.priority-lock')?document.activeElement.dataset.id:null;
  for(const id of selectedTasks)if(!state.tasks.some(t=>t.id===id))selectedTasks.delete(id);
  document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('selected',b.dataset.filter === filter); b.setAttribute('aria-pressed',String(b.dataset.filter === filter));});
  document.querySelectorAll('[data-priority-filter]').forEach(b=>b.setAttribute('aria-pressed',String(priorityFilters.has(Number(b.dataset.priorityFilter)))));
  $('#selection-count').textContent=`Выбрано: ${selectedTasks.size}`;
  document.querySelectorAll('[data-priority-assign]').forEach(b=>b.disabled=!selectedTasks.size);
  const term=$('#search').value;
  const tasks=visibleTasks(state,{view:filter,day:viewDay,query:term,priorities:[...priorityFilters]},new Date().toISOString());
  $('#task-list').innerHTML=tasks.length?tasks.map(t=>{
    const priority=priorityFor(t,viewDay),planned=t.planned_days?.includes(viewDay),keepPriority=t.status!=='completed'&&!!t.keep_priority;
    return `<article class="task-row ${selected===t.id?'chosen':''} ${t.status==='completed'?'completed':''}" data-testid="task-row" data-task-id="${escape(t.id)}"><button type="button" class="task-drag-handle" data-drag-id="${escape(t.id)}" aria-label="Переместить: ${escape(t.title)}" title="${t.status==='completed'?'Завершённые задачи расположены по времени завершения.':'Перетащите для изменения порядка. Клавиатура: стрелки вверх и вниз.'}" ${reorderBusy||t.status==='running'||t.status==='completed'?'disabled':''}>⠿</button><input type="checkbox" data-select-task="${escape(t.id)}" aria-label="Выбрать: ${escape(t.title)}" ${selectedTasks.has(t.id)?'checked':''}><span class="task-priority"><span class="priority-badge p${priority}" title="Приоритет ${priority}">${priority}</span><button type="button" class="priority-lock" data-action="toggleKeepPriority" data-id="${escape(t.id)}" aria-label="Сохранять приоритет на следующий день: ${escape(t.title)}" aria-pressed="${keepPriority}" title="${t.status==='completed'?'Задача завершена. Сохранение приоритета отключено.':keepPriority?'Сохранение приоритета включено. Нажмите, чтобы выключить.':'Сохранение приоритета выключено. Нажмите, чтобы включить.'}" ${t.status==='completed'||pendingPriorityLocks.has(t.id)?'disabled':''}><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="${keepPriority?'M8 10V7a4 4 0 0 1 8 0v3':'M8 10V7a4 4 0 0 1 7.7-1.5'}"/><path d="M12 14v3"/></svg></button></span><button class="task-select" data-action="select" data-id="${escape(t.id)}"><span class="task-name">${escape(t.title)}</span><span class="task-meta">${t.status==='running'?'Таймер запущен':t.status==='completed'?'Завершена':planned?'В плане':''}</span></button><div class="row-times"><span>За день: <b data-task-day="${escape(t.id)}"></b></span><span>Всего: <b data-task-time="${escape(t.id)}"></b></span></div><div class="row-actions"><button class="text-button" data-action="editTask" data-id="${escape(t.id)}">Изменить</button><button class="text-button" data-action="select" data-id="${escape(t.id)}" aria-label="История: ${escape(t.title)}">История</button>${t.status!=='completed'?`<button class="text-button" data-action="completeTask" data-id="${escape(t.id)}">Завершить</button><button class="text-button" data-action="${planned?'removeFromPlan':'addToPlan'}" data-id="${escape(t.id)}">${planned?'Из плана':'В план'}</button>`:''}<button class="text-button" data-action="deleteTask" data-id="${escape(t.id)}" aria-label="Удалить: ${escape(t.title)}">Удалить</button>${t.status!=='completed'?`<button class="task-control" data-action="${state.focus?.taskId===t.id?'stopFocus':t.status==='running'?'pauseTask':'startTask'}" data-id="${escape(t.id)}" data-testid="task-toggle" aria-label="${state.focus?.taskId===t.id?'Остановить концентрацию':t.status==='running'?'Приостановить':'Запустить'}: ${escape(t.title)}">${state.focus?.taskId===t.id?'■':t.status==='running'?'Ⅱ':'▶'}</button>`:''}</div></article>`;
  }).join(''):`<div class="empty"><h2>${state.tasks.length?'Нет задач для выбранных условий':'С чего начнём?'}</h2>${state.tasks.length?'':'<p>Добавьте задачу и запустите таймер.</p><button class="primary" data-action="create">Создать первую задачу</button>'}</div>`;
  if(focusedLock)document.querySelector(`.priority-lock[data-id="${CSS.escape(focusedLock)}"]:not(:disabled)`)?.focus({preventScroll:true});
  renderDetails();renderTimer();tick();
}
function cancelTaskDrag(){
 const drag=taskDrag;taskDrag=null;
 if(drag){cancelAnimationFrame(drag.frame);if(drag.handle.hasPointerCapture?.(drag.pointerId))drag.handle.releasePointerCapture(drag.pointerId);}
 document.querySelectorAll('.dragging,.drop-before,.drop-after').forEach(el=>el.classList.remove('dragging','drop-before','drop-after'));
}
function dragTarget(){
 if(!taskDrag)return;
 const d=taskDrag;document.querySelectorAll('.drop-before,.drop-after').forEach(el=>el.classList.remove('drop-before','drop-after'));d.target=null;
 const row=document.elementFromPoint(d.x,d.y)?.closest('[data-task-id]');
 if(!row||row.dataset.taskId===d.id||['running','completed'].includes(taskById(row.dataset.taskId).status))return;
 const box=row.getBoundingClientRect();d.target=row.dataset.taskId;d.position=d.y<box.top+box.height/2?'before':'after';row.classList.add('drop-'+d.position);
}
function scrollTaskDrag(){
 if(!taskDrag?.active)return;const d=taskDrag;
 if(d.y<65)window.scrollBy(0,-12);else if(d.y>innerHeight-65)window.scrollBy(0,12);
 dragTarget();d.frame=requestAnimationFrame(scrollTaskDrag);
}
async function moveTask(id,targetId,position,restoreFocus=false){
 if(reorderBusy)return;reorderBusy=true;
 try{await dispatch({type:'reorderTask',taskId:id,values:{targetId,position,view:filter,day:viewDay}});toast('Порядок сохранён');}
 catch(e){toast(e.message);}
 finally{reorderBusy=false;render();if(restoreFocus)document.querySelector(`[data-drag-id="${CSS.escape(id)}"]`)?.focus({preventScroll:true});}
}
document.addEventListener('pointerdown',event=>{
 const handle=event.target.closest('.task-drag-handle');if(!handle||handle.disabled||event.button!==0||reorderBusy)return;
 cancelTaskDrag();taskDrag={handle,id:handle.dataset.dragId,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,active:false};handle.setPointerCapture(event.pointerId);
});
document.addEventListener('pointermove',event=>{
 const d=taskDrag;if(!d||event.pointerId!==d.pointerId)return;d.x=event.clientX;d.y=event.clientY;
 if(!d.active&&Math.hypot(d.x-d.startX,d.y-d.startY)>5){d.active=true;d.handle.closest('[data-task-id]').classList.add('dragging');scrollTaskDrag();}
 if(d.active){event.preventDefault();dragTarget();}
},{passive:false});
document.addEventListener('pointerup',event=>{
 const d=taskDrag;if(!d||event.pointerId!==d.pointerId)return;const {id,target,position,active}=d;cancelTaskDrag();if(active&&target)void moveTask(id,target,position);
});
document.addEventListener('pointercancel',cancelTaskDrag);
document.addEventListener('lostpointercapture',event=>{if(taskDrag?.pointerId===event.pointerId)cancelTaskDrag();});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&taskDrag){cancelTaskDrag();return;}
 const handle=event.target.closest('.task-drag-handle');if(!handle||handle.disabled||!['ArrowUp','ArrowDown'].includes(event.key))return;
 event.preventDefault();if(reorderBusy)return;
 const handles=[...document.querySelectorAll('.task-drag-handle:not(:disabled)')],index=handles.indexOf(handle),target=handles[index+(event.key==='ArrowUp'?-1:1)];
 if(target)void moveTask(handle.dataset.dragId,target.dataset.dragId,event.key==='ArrowUp'?'before':'after',true);
});
function renderDetails() {
  const t = state.tasks.find(t => t.id === selected);
  if (!t) { if($('#details-dialog').open)$('#details-dialog').close(); $('#task-details').innerHTML = '<div class="details-empty"><span class="empty-symbol" aria-hidden="true">◷</span><h2>Время в деталях</h2><p>Выберите задачу, чтобы увидеть сессии и изменить записи.</p></div>'; return; }
  $('#task-details').innerHTML = `<div class="detail-heading"><p class="eyebrow">${t.status === 'completed' ? 'Завершена' : 'История задачи'}</p><h2>${escape(t.title)}</h2>${t.description ? `<p>${escape(t.description)}</p>` : ''}${t.result?`<p><strong>Результат:</strong> ${escape(t.result)}</p>`:''}<div class="detail-actions"><button class="secondary" data-action="editTask" data-id="${escape(t.id)}">Изменить</button>${t.status !== 'completed' ? `<button class="secondary" data-action="focus" data-id="${escape(t.id)}">Концентрация</button><button class="secondary" data-action="completeTask" data-id="${escape(t.id)}">Завершить</button>` : ''}<button class="danger" data-action="deleteTask" data-id="${escape(t.id)}">Удалить</button></div></div><div class="detail-total"><span>Всего по задаче</span><strong data-task-time="${escape(t.id)}">${duration(totalSeconds(t,new Date().toISOString()))}</strong></div><div class="history-heading"><h3>Сессии <span class="muted">· ${t.sessions.length}</span></h3><button class="text-button" data-action="addSession" data-id="${escape(t.id)}" data-testid="add-session">＋ Добавить</button></div><div data-testid="session-list">${t.sessions.length ? [...t.sessions].sort((a,b) => new Date(b.started_at)-new Date(a.started_at)).map(s => `<article class="session" data-testid="session"><div class="session-date">${escape(dateLabel(s.started_at))}${s.ended_at && localDate(s.started_at)!==localDate(s.ended_at) ? ` — ${escape(dateLabel(s.ended_at))}` : ''}</div><div class="session-top"><span>${clock(s.started_at)} — ${s.ended_at ? clock(s.ended_at) : 'сейчас'}</span><span class="session-duration" data-session-time="${escape(s.id)}">${duration(sessionSeconds(s,new Date().toISOString()))}</span></div>${s.comment ? `<p class="session-comment">${escape(s.comment)}</p>` : ''}${s.bitrix_record_id ? '<p class="session-date">Передана в Битрикс24</p>' : ''}<div class="session-actions"><button class="text-button" data-action="editSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Изменить</button><button class="text-button" data-action="deleteSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Удалить</button></div></article>`).join('') : '<p class="empty">Сессий пока нет.<br>Запустите таймер или добавьте запись.</p>'}</div>`;
}
function renderTimer() {
 const t=timerPanelTask(state);
 $('#active-timer').innerHTML=t?`<p class="timer-label">${t.status==='running'?'Текущая задача':'Приостановлена'}</p><p class="timer-title">${escape(t.title)}</p><div class="timer-value" id="live-clock" data-testid="live-clock" data-timer-task="${escape(t.id)}"></div><p class="timer-secondary">За день: <span data-task-day="${escape(t.id)}"></span><br>Всего: <span data-task-time="${escape(t.id)}"></span></p><div class="button-row"><button class="secondary" data-action="${state.focus?.taskId===t.id?'stopFocus':t.status==='running'?'pauseTask':'startTask'}" data-id="${escape(t.id)}">${state.focus?.taskId===t.id?'Остановить концентрацию':t.status==='running'?'Ⅱ Пауза':'▶ Продолжить'}</button><button class="secondary" data-action="completeTask" data-id="${escape(t.id)}">Завершить задачу</button></div>`:`<p class="timer-label">Таймер</p><p class="timer-secondary">${state.tasks.some(t=>t.status==='paused')?'Выберите ▶ у задачи, чтобы продолжить учёт времени.':'Молодец, все задачи выполнены!'}</p>`;
 $('#focus-status').textContent=state.focus?(state.focus.calendarClosed?'Отсчёт продолжается. Учёт времени за прошлый день завершён.':'Идёт отдельная сессия концентрации'):'Готов к запуску';
 $('#focus-panel-start').hidden=!!state.focus;$('#focus-panel-stop').hidden=!state.focus;
 document.querySelectorAll('[data-focus-minutes],#panel-focus-minutes').forEach(el=>el.disabled=!!state.focus);
 document.querySelectorAll('[data-focus-minutes]').forEach(el=>el.setAttribute('aria-pressed',String(Number(el.dataset.focusMinutes)===focusMinutes)));
 const previous=state.tasks.find(t=>t.id===state.focusResumeTaskId&&t.status!=='completed');$('#focus-resume').hidden=!previous;
 $('#focus-resume-title').textContent=previous?`Вернуться к задаче «${previous.title}»?`:'';
}
function tick() {
 refreshCloseWarning();
 const now=new Date(),iso=now.toISOString();
 $('#today-date').textContent=now.toLocaleDateString('ru-RU',{weekday:'long',day:'numeric',month:'long'});
 $('#day-total').textContent=`${viewDay===localDate()?'Сегодня':dateLabel(viewDay+'T12:00:00')} — ${duration(state.tasks.reduce((sum,t)=>sum+secondsOnDay(t,viewDay,iso),0))}`;
 document.querySelectorAll('[data-task-time]').forEach(el=>{const t=state.tasks.find(t=>t.id===el.dataset.taskTime);if(t)el.textContent=duration(totalSeconds(t,iso));});
 document.querySelectorAll('[data-task-day]').forEach(el=>{const t=state.tasks.find(t=>t.id===el.dataset.taskDay);if(t)el.textContent=duration(secondsOnDay(t,viewDay,iso));});
 document.querySelectorAll('[data-session-time]').forEach(el=>{const s=state.tasks.find(t=>t.id===selected)?.sessions.find(s=>s.id===el.dataset.sessionTime);if(s)el.textContent=duration(sessionSeconds(s,iso));});
 const live=$('#live-clock'),timerTask=state.tasks.find(t=>t.id===live?.dataset.timerTask);if(live&&timerTask)live.textContent=duration(sessionSeconds(timerTask.sessions.find(s=>!s.ended_at)||timerTask.sessions.at(-1),iso));
 $('#focus-clock').textContent=duration(state.focus?(new Date(state.focus.ends_at)-now)/1000:focusMinutes*60);
 const dayChanged=lastDay!==localDate();
 if(repo&&!reconciling&&(dayChanged||(state.focus&&new Date(state.focus.ends_at)<=now)||state.tasks.some(t=>t.sessions.some(s=>!s.ended_at&&localDay(s.started_at)!==localDate())))){
   reconciling=true;if(dayChanged){lastDay=localDate();if(filter==='today'){viewDay=lastDay;$('#view-day').value=viewDay;}}
   dispatch({type:'reconcile'}).catch(e=>errorAt('#global-error',e)).finally(()=>reconciling=false);
 }
}
let reportView='markdown',reportSnapshot=null;
function renderReport(){
 const extended=$('#report-extended').checked,table=reportView==='table',report=reportSnapshot;
 $('#report-title').textContent=`Отчёт за ${dateLabel(report.day+'T12:00:00')}`;
 $('#report-text').value=formatDayReport(report,{extended});
 $('#report-markdown').hidden=table;$('#report-table').hidden=!table;
 document.querySelectorAll('[data-action="reportView"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===reportView)));
 $('[data-action="copyReport"]').textContent=table?'Копировать Markdown':'Копировать';
 $('[data-action="downloadReport"]').textContent=table?'Скачать Markdown':'Скачать';
 if(!report.tasks.length){$('#report-table').innerHTML='<p class="empty">За '+escape(report.label)+' время не учтено.</p>';return;}
 const count=extended?5:2;
 $('#report-table').innerHTML=`<div class="report-table-scroll" tabindex="0" role="region" aria-label="Табличный отчёт за ${escape(report.label)}"><table class="day-report-table"><caption class="report-total">Итого за день <strong>${escape(report.total)}</strong></caption>${extended?'<colgroup><col class="report-date"><col class="report-date"><col class="report-duration"><col><col class="report-transfer"></colgroup><thead><tr><th scope="col">Начало</th><th scope="col">Окончание</th><th scope="col">Время</th><th scope="col">Комментарий</th><th scope="col">Передано</th></tr></thead>':'<thead><tr><th scope="col">Задача</th><th scope="col">Время</th></tr></thead>'}${report.tasks.map(t=>`<tbody class="${t.concentration?'report-focus':'report-task'}"><tr class="report-task-heading"><th scope="rowgroup" colspan="${count-1}">${escape(t.title)}</th><td class="report-time">${escape(t.elapsed)}</td></tr>${t.result?`<tr><td colspan="${count}" class="report-detail"><strong>Результат:</strong> ${escape(t.result)}</td></tr>`:''}${extended&&t.description?`<tr><td colspan="${count}" class="report-detail">${escape(t.description)}</td></tr>`:''}${extended?t.sessions.map(s=>`<tr class="report-session"><td>${escape(s.start)}</td><td>${escape(s.end)}</td><td class="report-time">${escape(s.elapsed)}</td><td class="report-comment">${escape(s.comment)||'—'}</td><td>${escape(s.transferred)||'—'}</td></tr>`).join(''):''}</tbody>`).join('')}</table></div>`;
}

function openEditor(title, fields, action, submit='Сохранить') { $('#editor-title').textContent=title; $('#editor-fields').innerHTML=fields; $('#editor-error').hidden=true; $('#editor-overwrite').hidden=true; $('#editor-form [type=submit]').textContent=submit; $('#editor-form [type=submit]').className='primary'; $('#editor-add-start').hidden=true; editorAction=action; addVoiceButtons($('#editor-form')); editorBaseline=editorSnapshot(); $('#editor-dialog').showModal(); refreshCloseWarning(); }
function taskEditor(id) {
  const original=id ? taskById(id) : null;
  const t=id ? {...original,day:viewDay,priority:priorityFor(original,viewDay)} : {title:'',description:'',result:'',keep_priority:false,priority:4,day:localDate()};
  openEditor(id ? 'Изменить задачу' : 'Новая задача', `<label class="field">Название<input name="title" data-testid="task-title" required maxlength="500" value="${escape(t.title)}" autofocus autocomplete="off"></label><label class="field">Описание<textarea name="description" maxlength="20000">${escape(t.description)}</textarea></label><label class="field">Результат<textarea name="result" maxlength="20000">${escape(t.result||'')}</textarea></label><label class="check-field"><input type="checkbox" name="keep_priority" ${t.status==='completed'?'disabled':t.keep_priority?'checked':''}>Сохранять приоритет при переносе на следующий день</label><div class="field-grid"><label class="field">Дата<input name="day" type="date" required value="${escape(t.day)}"></label><label class="field">Приоритет<select name="priority">${[1,2,3,4].map(p=>`<option value="${p}" ${Number(t.priority)===p?'selected':''}>${p}${p===1?' — высокий':p===4?' — обычный':''}</option>`).join('')}</select></label></div>`,async (form,force=false,startNow=false)=>{
    const fields={title:form.get('title'),description:form.get('description'),result:form.get('result'),keep_priority:form.has('keep_priority'),priority:Number(form.get('priority')),day:form.get('day')};
    const values=id ? Object.fromEntries(Object.entries(fields).filter(([key,value])=>value!==t[key])) : fields;
    if(id && 'day' in values)values.priority=fields.priority;
    const expected=id&&!force?Object.fromEntries(Object.keys(values).filter(key=>key!=='priority').map(key=>[key,original[key]])):undefined;
    if(expected && ('priority' in values || 'day' in values))expected.daily_priorities=original.daily_priorities;
    const next=await dispatch({type:id?'updateTask':startNow?'createAndStartTask':'createTask',taskId:id,values,expected,priorityDay:id?fields.day:undefined});
    if(!id){selected=next.tasks.at(-1)?.id;filter='today';viewDay=localDate();$('#view-day').value=viewDay;render();}
  },id?'Сохранить':'Добавить');
  if(!id){$('#editor-add-start').hidden=false;$('#editor-form [type=submit]').className='secondary';}
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
    if(action==='toggleKeepPriority'){
      if(pendingPriorityLocks.has(id)||taskById(id).status==='completed')return;
      const old=taskById(id).keep_priority;let restoreFocus=document.activeElement===button;
      const moved=event=>{if(event.target!==document.body&&!event.target.closest?.(`.priority-lock[data-id="${CSS.escape(id)}"]`))restoreFocus=false;};
      document.addEventListener('focusin',moved);document.addEventListener('pointerdown',moved);
      pendingPriorityLocks.add(id);render();
      try{await dispatch({type:'updateTask',taskId:id,values:{keep_priority:!old},expected:{keep_priority:old}});}
      finally{pendingPriorityLocks.delete(id);render();document.removeEventListener('focusin',moved);document.removeEventListener('pointerdown',moved);if(restoreFocus)document.querySelector(`.priority-lock[data-id="${CSS.escape(id)}"]`)?.focus({preventScroll:true});}
      return;
    }
    if(action==='select'){selected=id;render();if(!$('#details-dialog').open)$('#details-dialog').showModal();return;}
    if(action==='create'){taskEditor();return;}
    if(action==='editTask'){taskEditor(id);return;}
    if(action==='completeTask'){const t=taskById(id);openEditor('Завершить задачу',`<label class="field">Результат (необязательно)<textarea name="result" maxlength="20000">${escape(t.result||'')}</textarea></label>`,async form=>{const changed=form.get('result')!==(t.result||'');await dispatch({type:'completeTask',taskId:id,values:changed?{result:form.get('result')}:{},expected:changed?{result:t.result}:undefined});},'Завершить');return;}
    if(action==='addSession'||action==='editSession'){sessionEditor(id,button.dataset.session);return;}
    if(action==='deleteTask'){const t=taskById(id);confirm('Удалить задачу?',`«${t.title}» и все её сессии будут удалены. Отменить это действие нельзя.`,()=>dispatch({type:'deleteTask',taskId:id}));return;}
    if(action==='deleteSession'){confirm('Удалить сессию?','Запись и её время будут удалены из истории задачи.',()=>dispatch({type:'deleteSession',taskId:id,sessionId:button.dataset.session}));return;}
    if(action==='focus'){openEditor('Концентрация',`<label class="field">Длительность, минуты<input type="number" name="minutes" min="1" max="180" step="1" value="${focusMinutes}" required data-testid="focus-minutes"></label><p class="field-note">Текущая задача будет приостановлена. Время сохранится в отдельной задаче концентрации. В фоне сигнал не гарантирован.</p>`,form=>dispatch({type:'startFocus',values:{minutes:Number(form.get('minutes'))}}),'Начать');return;}
    if(action==='startPanelFocus'){await dispatch({type:'startFocus',values:{minutes:Number($('#panel-focus-minutes').value)}});return;}
    if(action==='addToPlan'||action==='removeFromPlan'){await dispatch({type:action,taskId:id,values:{day:viewDay}});return;}
    if(action==='report'){reportView='markdown';reportSnapshot=dayReportData(state,viewDay);renderReport();$('#report-status').textContent='';$('#report-dialog').showModal();return;}
    if(action==='reportView'){reportView=button.dataset.view;renderReport();return;}
    if(action==='copyReport'){await navigator.clipboard.writeText($('#report-text').value);$('#report-status').textContent='Отчёт скопирован.';return;}
    if(action==='downloadReport'){const url=URL.createObjectURL(new Blob([$('#report-text').value],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`tasktimer-report-${viewDay}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);return;}
    if(action==='printReport'){let printable=$('#report-print');if(!printable){printable=document.createElement('div');printable.id='report-print';printable.hidden=true;$('#report-dialog').append(printable);}printable.className=reportView==='table'?'report-print-table':'report-print-markdown';if(reportView==='table'){printable.replaceChildren(...[...$('#report-table').childNodes].map(node=>node.cloneNode(true)));}else{printable.textContent=$('#report-text').value;}window.print();return;}
    button.disabled=true;await dispatch({type:action,taskId:id});
  }catch(error){errorAt('#global-error',error);}finally{button.disabled=false;}
});
for(const [id,errorId,getAction] of [['editor-form','#editor-error',event=>()=>editorAction(new FormData($('#editor-form')),false,event.submitter?.id==='editor-add-start')],['confirm-form','#confirm-error',()=>confirmAction]]) $( `#${id}`).addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,dialog=form.closest('dialog');if(dialog.dataset.busy)return;dialog.dataset.busy='true';const buttons=form.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await getAction(event)();dialog.close();}catch(error){errorAt(errorId,error);if(id==='editor-form')$('#editor-overwrite').hidden=error.name!=='ConcurrentEditError';}finally{delete dialog.dataset.busy;buttons.forEach(b=>b.disabled=false);}});
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(dialog.dataset.busy)event.preventDefault();}));
$('#new-task').addEventListener('click',()=>taskEditor());
$('#search').addEventListener('input',render);
$('#view-day').addEventListener('change',()=>{if(!$('#view-day').value)return;viewDay=$('#view-day').value;filter='date';render();});
$('#task-list').addEventListener('change',event=>{const id=event.target.dataset.selectTask;if(id){if(event.target.checked)selectedTasks.add(id);else selectedTasks.delete(id);render();}});
$('#priority-filters').addEventListener('click',event=>{const b=event.target.closest('[data-priority-filter]');if(!b)return;const p=Number(b.dataset.priorityFilter);if(priorityFilters.has(p)){if(priorityFilters.size>1)priorityFilters.delete(p);}else priorityFilters.add(p);render();});
$('#priority-assign').addEventListener('click',async event=>{const b=event.target.closest('[data-priority-assign]');if(!b)return;try{await dispatch({type:'assignPriority',taskIds:[...selectedTasks],values:{day:viewDay,priority:Number(b.dataset.priorityAssign)}});selectedTasks.clear();render();}catch(e){errorAt('#global-error',e);}});
document.querySelectorAll('[data-focus-minutes]').forEach(b=>b.addEventListener('click',()=>{focusMinutes=Number(b.dataset.focusMinutes);$('#panel-focus-minutes').value=focusMinutes;renderTimer();tick();}));
$('#panel-focus-minutes').addEventListener('input',()=>{focusMinutes=Number($('#panel-focus-minutes').value);renderTimer();tick();});
$('#report-extended').addEventListener('change',renderReport);
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{selectedTasks.clear();filter=b.dataset.filter;if(filter==='today'){viewDay=localDate();$('#view-day').value=viewDay;}render();}));
$('#settings-button').addEventListener('click',()=>{loadReminderSettings();$('#settings-dialog').showModal();});
$('#export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#import-error',e)));
$('#confirm-export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#confirm-error',e)));
$('#import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>20*1024*1024)throw new Error('Файл слишком большой. Максимум 20 МБ.');const imported=validateBackup(JSON.parse(await file.text()));$('#import-error').hidden=true;confirm(imported.syncDocument?'Объединить журнал из копии?':'Заменить данные копией?',imported.syncDocument?'Журнал копии объединится с текущим. Удаления и конфликтующие варианты сохранятся для выбора.':`В копии задач: ${imported.tasks.length}. Все текущие задачи и сессии будут заменены. Сначала рекомендуем скачать текущую копию.`,async()=>{await dispatch({type:'replaceState',values:imported});selected=null;render();toast('Резервная копия восстановлена.');},{label:imported.syncDocument?'Объединить':'Заменить данные',backup:true});}catch(error){errorAt('#import-error',error);}finally{event.target.value='';}});
$('#enable-notifications').addEventListener('click',async()=>{try{if(!('Notification'in window))throw new Error('Этот браузер не поддерживает уведомления.');const permission=await Notification.requestPermission();$('#notification-status').textContent=permission==='granted'?'Уведомления разрешены.':permission==='denied'?'Уведомления запрещены в настройках браузера.':'Разрешение не выдано.';}catch(error){$('#notification-status').textContent=error.message;}});
function connection(){ $('#connection').textContent=navigator.onLine?'':'Офлайн'; }window.addEventListener('online',connection);window.addEventListener('offline',connection);connection();
let reminderExpected=null,reminderBusy=false;
function reminderSettingsSnapshot(){return JSON.stringify([$('#reminder-enabled').checked,$('#reminder-minutes').value]);}
function reminderSettingsDirty(){return $('#settings-dialog').open&&reminderSettingsBaseline&&reminderSettingsSnapshot()!==reminderSettingsBaseline;}
function loadReminderSettings(){const r=state.reminder||{enabled:true,minutes:40};$('#reminder-enabled').checked=r.enabled;$('#reminder-minutes').value=r.minutes;reminderSettingsBaseline=reminderSettingsSnapshot();$('#reminder-settings-status').textContent='';}
$('#reminder-settings').addEventListener('input',refreshCloseWarning);
$('#reminder-settings').addEventListener('submit',async event=>{
 event.preventDefault();const submitted=reminderSettingsSnapshot();$('#reminder-save').disabled=true;
 try{await dispatch({type:'reminder',values:{action:'settings',enabled:$('#reminder-enabled').checked,minutes:Number($('#reminder-minutes').value)}});reminderSettingsBaseline=submitted;$('#reminder-settings-status').textContent='Сохранено';refreshCloseWarning();}
 catch(e){$('#reminder-settings-status').textContent=e.message;}finally{$('#reminder-save').disabled=false;}
});
function reminderVisible(){return document.visibilityState==='visible'&&document.hasFocus();}
function sameReminder(a,b){return a&&b&&a.generation===b.generation&&a.taskId===b.taskId&&a.sessionId===b.sessionId&&a.started_at===b.started_at&&a.dueAt===b.dueAt;}
function reminderButtons(disabled){$('#reminder-continue').disabled=disabled;$('#reminder-stop').disabled=disabled;}
$('#reminder-dialog').addEventListener('cancel',event=>event.preventDefault());
async function answerReminder(action){
 if(reminderBusy||!reminderExpected)return;reminderBusy=true;reminderButtons(true);
 try{await dispatch({type:'reminder',values:{action,expected:reminderExpected}});$('#reminder-dialog').close();reminderExpected=null;}
 catch(e){errorAt('#reminder-error',e);}finally{reminderBusy=false;reminderButtons(false);}
}
$('#reminder-continue').addEventListener('click',()=>answerReminder('continue'));
$('#reminder-stop').addEventListener('click',()=>answerReminder('stop'));
async function checkReminder(){
 syncReminderAttention();
 if(!repo||reminderBusy)return;
 const dialog=$('#reminder-dialog'),p=state.reminder?.pending;
 if(dialog.open&&!sameReminder(p,reminderExpected)){dialog.close();reminderExpected=null;}
 if(state.sync?.projectionError||state.sync?.conflicts?.length){if(dialog.open)dialog.close();return;}
 if(!p)return;
 if(p.deadline&&Date.now()>=Date.parse(p.deadline)){
   reminderBusy=true;try{await dispatch({type:'reconcile'});if(dialog.open)dialog.close();reminderExpected=null;}catch(e){errorAt('#global-error',e);}finally{reminderBusy=false;}return;
 }
 if(dialog.open){$('#reminder-countdown').textContent=p.deadline?`Без ответа таймер остановится через ${duration((Date.parse(p.deadline)-Date.now())/1000)}.`:'Подготовка напоминания…';return;}
 if(Date.now()<Date.parse(p.dueAt)||!reminderVisible()||document.querySelector('dialog[open]'))return;
 reminderBusy=true;reminderExpected=structuredClone(p);reminderButtons(true);$('#reminder-error').hidden=true;
 $('#reminder-task').textContent=state.tasks.find(t=>t.id===p.taskId)?.title||'';
 $('#reminder-countdown').textContent=`Без ответа таймер остановится через ${duration(Math.max(0,(Date.parse(p.deadline)-Date.now())/1000))}.`;
 try{
   dialog.showModal();
   // Record actual display for answer guards; display never extends the deadline.
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   if(!dialog.open||!reminderVisible()){dialog.close();reminderExpected=null;return;}
   const next=await dispatch({type:'reminder',values:{action:'shown',expected:reminderExpected}});
   if(!sameReminder(next.reminder?.pending,reminderExpected)){dialog.close();reminderExpected=null;return;}
   reminderExpected=structuredClone(next.reminder.pending);
 }catch(e){dialog.close();reminderExpected=null;errorAt('#global-error',e);}finally{reminderBusy=false;reminderButtons(false);}
}
window.addEventListener('focus',()=>checkReminder());
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')checkReminder();});
try{repo=await openRepository();const initial=await repo.read();if(initial.tasks.some(t=>t.status!=='completed')&&!visibleTasks(initial,{view:'today',day:viewDay}).length)filter='progress';accept(initial);repo.subscribe((next,error)=>{if(error){errorAt('#global-error',error);return;}if(next?.tasks)accept(next);else repo.read().then(accept).catch(e=>errorAt('#global-error',e));});}catch(error){errorAt('#global-error',error);$('#task-list').innerHTML='<p class="empty">Не удалось открыть локальные данные.<br>Проверьте разрешения браузера и перезагрузите страницу.</p>';}
window.addEventListener('tasktimer:before-update', event => {
 const confirmedRisks=closeRisks();
 event.detail.beforeReload?.(()=>{
   // Only the exact accepted worker invokes this, immediately before reloading.
   // New edits/recordings/writes retain the standard browser confirmation.
   if(pendingWrites.size||closeRisks()!==confirmedRisks)return;
   window.removeEventListener('beforeunload',warnBeforeClose);closeWarningAttached=false;
   setTimeout(refreshCloseWarning,0); // Restore protection if navigation does not occur.
 });
 event.detail.waitUntil((async () => { if (!repo) throw new Error('Хранилище недоступно. Обновление отменено.'); await Promise.all([...pendingWrites]); await repo.read(); })());
});
setInterval(()=>{tick();checkReminder();},1000);

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
function showSyncTarget(){
 const form=new FormData($('#sync-form'));const output=$('#sync-target');
 if(!String(form.get('url')||'').trim()){output.textContent='';return;}
 try{const addresses=resolveWebDavUrls(form.get('url'),form.get('filePath'));output.textContent='Файл синхронизации: '+addresses.url;}
 catch(e){output.textContent=e.message;}
}
$('#sync-form [name=url]').addEventListener('input',showSyncTarget);
$('#sync-form [name=filePath]').addEventListener('input',showSyncTarget);
$('#sync-form').addEventListener('submit',async event=>{
 event.preventDefault();if(syncAbort)return;const form=new FormData(event.currentTarget);syncAbort=new AbortController();$('#sync-submit').disabled=true;$('#sync-cancel').hidden=false;$('#sync-error').hidden=true;$('#sync-status').textContent='Синхронизация…';
 try{const addresses=resolveWebDavUrls(form.get('url'),form.get('filePath'));const url=new URL(addresses.url);const options={username:form.get('username'),password:form.get('password')};const legacyClient=createWebDavClient({url:addresses.legacyUrl,...options});const client=createWebDavClient({url:url.href,...options});const targetKey=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(url.href+'\n'+options.username))),b=>b.toString(16).padStart(2,'0')).join('');accept(await synchronize(repo,client,{signal:syncAbort.signal,legacyClient,targetKey}));$('#sync-status').textContent=state.sync?.conflicts.length||state.sync?.projectionError?'Обмен завершён; разрешите конфликты ниже.':'Синхронизация завершена.';}catch(e){if(syncAbort.signal.aborted)$('#sync-status').textContent='Обмен отменён. Уже сохранённые данные остаются на устройстве.';else{errorAt('#sync-error',e);$('#sync-status').textContent='Синхронизация не завершена.';}}finally{syncAbort=null;$('#sync-submit').disabled=false;$('#sync-cancel').hidden=true;}
});
$('#sync-cancel').addEventListener('click',()=>syncAbort?.abort());
$('#sync-backup').addEventListener('click',async()=>{try{const backup=await repo.migrationBackup();if(!backup)throw new Error('Копия до первого обмена отсутствует.');const url=URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='tasktimer-before-webdav.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){errorAt('#sync-error',e);}});

installVoiceInterface({onChange:({phase,text,open})=>{const risk=open&&(['starting','recording','decoding'].includes(phase)||text.trim())?JSON.stringify({phase,text}):'';if(risk!==voiceRisk){voiceRevision++;voiceRisk=risk;}refreshCloseWarning();},confirmRemoval:action=>confirm('Удалить голосовую модель?','Диктовка станет недоступной до повторной загрузки. Задачи и записи сохранятся.',action)});

$('#editor-overwrite').addEventListener('click',()=>confirm('Заменить изменённые поля вашим вариантом?','Текущие значения показаны в ошибке редактора. Только изменённые вами поля будут заменены.',async()=>{await editorAction(new FormData($('#editor-form')),true);$('#editor-dialog').close();},{label:'Сохранить мой вариант'}));
