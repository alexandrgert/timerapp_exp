import {installVoiceInterface,addVoiceButtons} from './voice-ui.mjs';
import { createWebDavClient } from './webdav-client.mjs';
import { synchronize } from './sync-controller.mjs';
import { remoteV2Path } from './sync-protocol.mjs';
import { openRepository } from './repository.mjs';
import { localDay, priorityFor, secondsOnDay, visibleTasks, buildDayReport } from './desktop-domain.mjs';
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
let viewDay=localDate(), focusMinutes=20, lastDay=localDate();
const selectedTasks=new Set(), priorityFilters=new Set([1,2,3,4]);
$('#view-day').value=viewDay;
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
  for(const id of selectedTasks)if(!state.tasks.some(t=>t.id===id))selectedTasks.delete(id);
  document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('selected',b.dataset.filter === filter); b.setAttribute('aria-pressed',String(b.dataset.filter === filter));});
  document.querySelectorAll('[data-priority-filter]').forEach(b=>b.setAttribute('aria-pressed',String(priorityFilters.has(Number(b.dataset.priorityFilter)))));
  $('#selection-count').textContent=`Выбрано: ${selectedTasks.size}`;
  document.querySelectorAll('[data-priority-assign]').forEach(b=>b.disabled=!selectedTasks.size);
  const term=$('#search').value;
  const tasks=visibleTasks(state,{view:filter,day:viewDay,query:term,priorities:[...priorityFilters]},new Date().toISOString());
  $('#task-list').innerHTML=tasks.length?tasks.map(t=>{
    const priority=priorityFor(t,viewDay),planned=t.planned_days?.includes(viewDay);
    return `<article class="task-row ${selected===t.id?'chosen':''} ${t.status==='completed'?'completed':''}" data-testid="task-row"><input type="checkbox" data-select-task="${escape(t.id)}" aria-label="Выбрать: ${escape(t.title)}" ${selectedTasks.has(t.id)?'checked':''}><span class="priority-badge p${priority}" title="Приоритет ${priority}">${priority}</span><button class="task-select" data-action="select" data-id="${escape(t.id)}"><span class="task-name">${escape(t.title)}</span><span class="task-meta">${t.status==='running'?'Таймер запущен':t.status==='completed'?'Завершена':planned?'В плане':''}</span></button><div class="row-times"><span>За день: <b data-task-day="${escape(t.id)}"></b></span><span>Всего: <b data-task-time="${escape(t.id)}"></b></span></div><div class="row-actions"><button class="text-button" data-action="editTask" data-id="${escape(t.id)}">Изменить</button><button class="text-button" data-action="select" data-id="${escape(t.id)}" aria-label="История: ${escape(t.title)}">История</button>${t.status!=='completed'?`<button class="text-button" data-action="completeTask" data-id="${escape(t.id)}">Завершить</button><button class="text-button" data-action="${planned?'removeFromPlan':'addToPlan'}" data-id="${escape(t.id)}">${planned?'Из плана':'В план'}</button>`:''}<button class="text-button" data-action="deleteTask" data-id="${escape(t.id)}" aria-label="Удалить: ${escape(t.title)}">Удалить</button>${t.status!=='completed'?`<button class="task-control" data-action="${state.focus?.taskId===t.id?'stopFocus':t.status==='running'?'pauseTask':'startTask'}" data-id="${escape(t.id)}" data-testid="task-toggle" aria-label="${state.focus?.taskId===t.id?'Остановить концентрацию':t.status==='running'?'Приостановить':'Запустить'}: ${escape(t.title)}">${state.focus?.taskId===t.id?'■':t.status==='running'?'Ⅱ':'▶'}</button>`:''}</div></article>`;
  }).join(''):`<div class="empty"><h2>${state.tasks.length?'Нет задач для выбранных условий':'С чего начнём?'}</h2>${state.tasks.length?'':'<p>Добавьте задачу и запустите таймер.</p><button class="primary" data-action="create">Создать первую задачу</button>'}</div>`;
  renderDetails();renderTimer();tick();
}
function renderDetails() {
  const t = state.tasks.find(t => t.id === selected);
  if (!t) { if($('#details-dialog').open)$('#details-dialog').close(); $('#task-details').innerHTML = '<div class="details-empty"><span class="empty-symbol" aria-hidden="true">◷</span><h2>Время в деталях</h2><p>Выберите задачу, чтобы увидеть сессии и изменить записи.</p></div>'; return; }
  $('#task-details').innerHTML = `<div class="detail-heading"><p class="eyebrow">${t.status === 'completed' ? 'Завершена' : 'История задачи'}</p><h2>${escape(t.title)}</h2>${t.description ? `<p>${escape(t.description)}</p>` : ''}${t.result?`<p><strong>Результат:</strong> ${escape(t.result)}</p>`:''}<div class="detail-actions"><button class="secondary" data-action="editTask" data-id="${escape(t.id)}">Изменить</button>${t.status !== 'completed' ? `<button class="secondary" data-action="focus" data-id="${escape(t.id)}">Концентрация</button><button class="secondary" data-action="completeTask" data-id="${escape(t.id)}">Завершить</button>` : ''}<button class="danger" data-action="deleteTask" data-id="${escape(t.id)}">Удалить</button></div></div><div class="detail-total"><span>Всего по задаче</span><strong data-task-time="${escape(t.id)}">${duration(totalSeconds(t,new Date().toISOString()))}</strong></div><div class="history-heading"><h3>Сессии <span class="muted">· ${t.sessions.length}</span></h3><button class="text-button" data-action="addSession" data-id="${escape(t.id)}" data-testid="add-session">＋ Добавить</button></div><div data-testid="session-list">${t.sessions.length ? [...t.sessions].sort((a,b) => new Date(b.started_at)-new Date(a.started_at)).map(s => `<article class="session" data-testid="session"><div class="session-date">${escape(dateLabel(s.started_at))}${s.ended_at && localDate(s.started_at)!==localDate(s.ended_at) ? ` — ${escape(dateLabel(s.ended_at))}` : ''}</div><div class="session-top"><span>${clock(s.started_at)} — ${s.ended_at ? clock(s.ended_at) : 'сейчас'}</span><span class="session-duration" data-session-time="${escape(s.id)}">${duration(sessionSeconds(s,new Date().toISOString()))}</span></div>${s.comment ? `<p class="session-comment">${escape(s.comment)}</p>` : ''}${s.bitrix_record_id ? '<p class="session-date">Передана в Битрикс24</p>' : ''}<div class="session-actions"><button class="text-button" data-action="editSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Изменить</button><button class="text-button" data-action="deleteSession" data-id="${escape(t.id)}" data-session="${escape(s.id)}">Удалить</button></div></article>`).join('') : '<p class="empty">Сессий пока нет.<br>Запустите таймер или добавьте запись.</p>'}</div>`;
}
function renderTimer() {
 const t=state.tasks.find(t=>t.status==='running')||state.tasks.filter(t=>t.status!=='completed'&&t.sessions.length).sort((a,b)=>Date.parse(b.sessions.at(-1).ended_at||b.sessions.at(-1).started_at)-Date.parse(a.sessions.at(-1).ended_at||a.sessions.at(-1).started_at))[0];
 $('#active-timer').innerHTML=t?`<p class="timer-label">${t.status==='running'?'Текущая задача':'Приостановлена'}</p><p class="timer-title">${escape(t.title)}</p><div class="timer-value" id="live-clock" data-testid="live-clock" data-timer-task="${escape(t.id)}"></div><p class="timer-secondary">За день: <span data-task-day="${escape(t.id)}"></span><br>Всего: <span data-task-time="${escape(t.id)}"></span></p><div class="button-row"><button class="secondary" data-action="${state.focus?.taskId===t.id?'stopFocus':t.status==='running'?'pauseTask':'startTask'}" data-id="${escape(t.id)}">${state.focus?.taskId===t.id?'Остановить концентрацию':t.status==='running'?'Ⅱ Пауза':'▶ Продолжить'}</button><button class="secondary" data-action="completeTask" data-id="${escape(t.id)}">Завершить задачу</button></div>`:'<p class="timer-label">Таймер</p><p class="timer-secondary">Выберите ▶ у задачи, чтобы начать учёт времени.</p>';
 $('#focus-status').textContent=state.focus?(state.focus.calendarClosed?'Отсчёт продолжается. Учёт времени за прошлый день завершён.':'Идёт отдельная сессия концентрации'):'Готов к запуску';
 $('#focus-panel-start').hidden=!!state.focus;$('#focus-panel-stop').hidden=!state.focus;
 document.querySelectorAll('[data-focus-minutes],#panel-focus-minutes').forEach(el=>el.disabled=!!state.focus);
 document.querySelectorAll('[data-focus-minutes]').forEach(el=>el.setAttribute('aria-pressed',String(Number(el.dataset.focusMinutes)===focusMinutes)));
 const previous=state.tasks.find(t=>t.id===state.focusResumeTaskId&&t.status!=='completed');$('#focus-resume').hidden=!previous;
 $('#focus-resume-title').textContent=previous?`Вернуться к задаче «${previous.title}»?`:'';
}
function tick() {
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
function renderReport(){ $('#report-title').textContent=`Отчёт за ${dateLabel(viewDay+'T12:00:00')}`;$('#report-text').value=buildDayReport(state,viewDay,{extended:$('#report-extended').checked,now:new Date().toISOString()}); }
function openEditor(title, fields, action, submit='Сохранить') { $('#editor-title').textContent=title; $('#editor-fields').innerHTML=fields; $('#editor-error').hidden=true; $('#editor-overwrite').hidden=true; $('#editor-form [type=submit]').textContent=submit; editorAction=action; addVoiceButtons($('#editor-form')); $('#editor-dialog').showModal(); }
function taskEditor(id) {
  const t=id ? taskById(id) : {title:'',description:'',result:'',keep_priority:false,priority:4,day:localDate()};
  openEditor(id ? 'Изменить задачу' : 'Новая задача', `<label class="field">Название<input name="title" data-testid="task-title" required maxlength="500" value="${escape(t.title)}" autofocus autocomplete="off"></label><label class="field">Описание<textarea name="description" maxlength="20000">${escape(t.description)}</textarea></label><label class="field">Результат<textarea name="result" maxlength="20000">${escape(t.result||'')}</textarea></label><label class="check-field"><input type="checkbox" name="keep_priority" ${t.keep_priority?'checked':''}>Сохранять приоритет при переносе на следующий день</label><div class="field-grid"><label class="field">Дата<input name="day" type="date" required value="${escape(t.day)}"></label><label class="field">Приоритет<select name="priority">${[1,2,3,4].map(p=>`<option value="${p}" ${Number(t.priority)===p?'selected':''}>${p}${p===1?' — высокий':p===4?' — обычный':''}</option>`).join('')}</select></label></div>`,async (form,force=false)=>{
    const fields={title:form.get('title'),description:form.get('description'),result:form.get('result'),keep_priority:form.has('keep_priority'),priority:Number(form.get('priority')),day:form.get('day')};
    const values=id ? Object.fromEntries(Object.entries(fields).filter(([key,value])=>value!==t[key])) : fields;
    const expected=id&&!force?Object.fromEntries(Object.keys(values).map(key=>[key,t[key]])):undefined;
    const next=await dispatch({type:id?'updateTask':'createTask',taskId:id,values,expected});
    if(!id){selected=next.tasks.at(-1)?.id;filter='today';viewDay=localDate();$('#view-day').value=viewDay;render();}
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
    if(action==='report'){renderReport();$('#report-status').textContent='';$('#report-dialog').showModal();return;}
    if(action==='copyReport'){await navigator.clipboard.writeText($('#report-text').value);$('#report-status').textContent='Отчёт скопирован.';return;}
    if(action==='downloadReport'){const url=URL.createObjectURL(new Blob([$('#report-text').value],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`tasktimer-report-${viewDay}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);return;}
    if(action==='printReport'){let printable=$('#report-print');if(!printable){printable=document.createElement('pre');printable.id='report-print';printable.hidden=true;$('#report-dialog').append(printable);}printable.textContent=$('#report-text').value;window.print();return;}
    button.disabled=true;await dispatch({type:action,taskId:id});
  }catch(error){errorAt('#global-error',error);}finally{button.disabled=false;}
});
for(const [id,errorId,getAction] of [['editor-form','#editor-error',()=>()=>editorAction(new FormData($('#editor-form')))],['confirm-form','#confirm-error',()=>confirmAction]]) $( `#${id}`).addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,dialog=form.closest('dialog');if(dialog.dataset.busy)return;dialog.dataset.busy='true';const buttons=form.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);try{await getAction()();dialog.close();}catch(error){errorAt(errorId,error);if(id==='editor-form')$('#editor-overwrite').hidden=error.name!=='ConcurrentEditError';}finally{delete dialog.dataset.busy;buttons.forEach(b=>b.disabled=false);}});
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(dialog.dataset.busy)event.preventDefault();}));
$('#new-task').addEventListener('click',()=>taskEditor());
$('#search').addEventListener('input',render);
$('#view-day').addEventListener('change',()=>{if(!$('#view-day').value)return;viewDay=$('#view-day').value;filter='date';render();});
$('#task-list').addEventListener('change',event=>{const id=event.target.dataset.selectTask;if(id){if(event.target.checked)selectedTasks.add(id);else selectedTasks.delete(id);render();}});
$('#priority-filters').addEventListener('click',event=>{const b=event.target.closest('[data-priority-filter]');if(!b)return;const p=Number(b.dataset.priorityFilter);if(priorityFilters.has(p)){if(priorityFilters.size>1)priorityFilters.delete(p);}else priorityFilters.add(p);render();});
$('#priority-assign').addEventListener('click',async event=>{const b=event.target.closest('[data-priority-assign]');if(!b)return;try{await dispatch({type:'assignPriority',taskIds:[...selectedTasks],values:{day:viewDay,priority:Number(b.dataset.priorityAssign)}});}catch(e){errorAt('#global-error',e);}});
document.querySelectorAll('[data-focus-minutes]').forEach(b=>b.addEventListener('click',()=>{focusMinutes=Number(b.dataset.focusMinutes);$('#panel-focus-minutes').value=focusMinutes;renderTimer();tick();}));
$('#panel-focus-minutes').addEventListener('input',()=>{focusMinutes=Number($('#panel-focus-minutes').value);renderTimer();tick();});
$('#report-extended').addEventListener('change',renderReport);
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;if(filter==='today'){viewDay=localDate();$('#view-day').value=viewDay;}render();}));
$('#settings-button').addEventListener('click',()=>$('#settings-dialog').showModal());
$('#export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#import-error',e)));
$('#confirm-export').addEventListener('click',()=>exportBackup().catch(e=>errorAt('#confirm-error',e)));
$('#import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>20*1024*1024)throw new Error('Файл слишком большой. Максимум 20 МБ.');const imported=validateBackup(JSON.parse(await file.text()));$('#import-error').hidden=true;confirm(imported.syncDocument?'Объединить журнал из копии?':'Заменить данные копией?',imported.syncDocument?'Журнал копии объединится с текущим. Удаления и конфликтующие варианты сохранятся для выбора.':`В копии задач: ${imported.tasks.length}. Все текущие задачи и сессии будут заменены. Сначала рекомендуем скачать текущую копию.`,async()=>{await dispatch({type:'replaceState',values:imported});selected=null;render();toast('Резервная копия восстановлена.');},{label:imported.syncDocument?'Объединить':'Заменить данные',backup:true});}catch(error){errorAt('#import-error',error);}finally{event.target.value='';}});
$('#enable-notifications').addEventListener('click',async()=>{try{if(!('Notification'in window))throw new Error('Этот браузер не поддерживает уведомления.');const permission=await Notification.requestPermission();$('#notification-status').textContent=permission==='granted'?'Уведомления разрешены.':permission==='denied'?'Уведомления запрещены в настройках браузера.':'Разрешение не выдано.';}catch(error){$('#notification-status').textContent=error.message;}});
function connection(){ $('#connection').textContent=navigator.onLine?'':'Офлайн'; }window.addEventListener('online',connection);window.addEventListener('offline',connection);connection();
try{repo=await openRepository();const initial=await repo.read();if(initial.tasks.some(t=>t.status!=='completed')&&!visibleTasks(initial,{view:'today',day:viewDay}).length)filter='progress';accept(initial);repo.subscribe((next,error)=>{if(error){errorAt('#global-error',error);return;}if(next?.tasks)accept(next);else repo.read().then(accept).catch(e=>errorAt('#global-error',e));});}catch(error){errorAt('#global-error',error);$('#task-list').innerHTML='<p class="empty">Не удалось открыть локальные данные.<br>Проверьте разрешения браузера и перезагрузите страницу.</p>';}
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
