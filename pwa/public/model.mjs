import {localDay, priorityFor} from './desktop-domain.mjs';
const clone = value => structuredClone(value);
const fail = message => { throw new Error(message); };
const id = () => globalThis.crypto.randomUUID();
const active = task => task.sessions.find(s => s.ended_at === null);
export const initialState = () => ({schemaVersion: 1, tasks: [], focus: null});
function calendar(value) {
 if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) fail('Укажите корректную дату');
 const [y,m,d]=value.split('-').map(Number);
 if(y<1 || m<1 || m>12 || d<1 || d>new Date(Date.UTC(y,m,0)).getUTCDate()) fail('Укажите существующую дату');
 return value;
}
function timestamp(value) {
 if(typeof value !== 'string') fail('Укажите дату и время');
 const m=/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
 if(!m) fail('Некорректный формат даты и времени');
 calendar(m[1]);
 if(+m[2]>23 || +m[3]>59 || +(m[4]||0)>59) fail('Некорректное время');
 if(m[6] && m[6]!=='Z' && (+m[6].slice(1,3)>23 || +m[6].slice(4)>59)) fail('Некорректный часовой пояс');
 const n=Date.parse(value); if(!Number.isFinite(n)) fail('Некорректная дата и время'); return n;
}
function taskFields(values, task, now) {
 if('title' in values) { if(typeof values.title!=='string' || !values.title.trim()) fail('Введите название задачи'); task.title=values.title.trim(); }
 if('description' in values) {if(typeof values.description!=='string') fail('Описание должно быть текстом'); task.description=values.description;}
 if('result' in values){if(typeof values.result!=='string')fail('Результат должен быть текстом');task.result=values.result.trim();}
 if('keep_priority' in values){if(typeof values.keep_priority!=='boolean')fail('Некорректное сохранение приоритета');task.keep_priority=values.keep_priority;}
 if('day' in values) task.day=calendar(values.day);
 if('priority' in values) {if(!Number.isInteger(values.priority)||values.priority<1||values.priority>4) fail('Приоритет должен быть от 1 до 4'); task.priority=values.priority;}
 if('priority' in values || 'day' in values){task.daily_priorities={...task.daily_priorities};task.daily_priorities[task.day]=task.priority;}
}
function close(task, now) { const session=active(task); if(session) {if(timestamp(now)<timestamp(session.started_at)) fail('Время окончания раньше начала сессии'); session.ended_at=now;} if(task.status==='running')task.status='paused'; }
function start(state, task, now) {
 if(task.status==='completed'){task.status='open';task.completed_at=null;}
 if(active(task)){if(timestamp(active(task).started_at)>timestamp(now))fail('Текущее время раньше начала сессии. Проверьте часы устройства или исправьте сессию.');return;}
 for(const other of state.tasks)if(other!==task && active(other))close(other,now);
 if(state.focus && state.focus.taskId!==null && state.focus.taskId!==task.id)finishFocus(state,now);
 task.sessions.push({id:id(),started_at:now,ended_at:null,comment:'',bitrix_record_id:null}); task.status='running';
}
function finishFocus(state, now) {
 const f=state.focus;if(!f)return;
 const focused=state.tasks.find(t=>t.id===f.taskId);
 if(focused){close(focused,now);if(f.kind==='desktop'){focused.status='completed';focused.completed_at=now;}}
 if(f.kind==='desktop')state.focusResumeTaskId=state.tasks.some(t=>t.id===f.previousTaskId&&t.status!=='completed')?f.previousTaskId:null;
 state.focus=null;
}
function reconcileCalendar(s, now) {
 const today=localDay(now);
 for(const task of s.tasks){
 if(!Array.isArray(task.planned_days))task.planned_days=[task.day];
 if(!task.daily_priorities)task.daily_priorities=task.priority!==4?{[task.day]:task.priority}:{};
 const session=active(task);
 if(session&&localDay(session.started_at)<today){
 const end=new Date(session.started_at);end.setHours(23,59,59,0);
 // Desktop closes at 23:59:59; a subsecond start after that boundary must never yield a negative interval.
 const at=new Date(Math.max(end.getTime(),timestamp(session.started_at))).toISOString();
 if(s.focus?.taskId===task.id)finishFocus(s,timestamp(s.focus.ends_at)<timestamp(at)?s.focus.ends_at:at);else close(task,at);
 }
 }
 if(s.plan_rollover_day!==today){
 const yesterday=new Date(now);yesterday.setDate(yesterday.getDate()-1);const day=localDay(yesterday);
 for(const task of s.tasks)if(task.status!=='completed'&&task.planned_days.includes(day)&&!task.planned_days.includes(today)){
 task.planned_days.push(today);
 if(task.keep_priority&&Object.hasOwn(task.daily_priorities,day))task.daily_priorities[today]=task.daily_priorities[day];
 }
 s.plan_rollover_day=today;
 }
 for(const task of s.tasks)task.priority=priorityFor(task,task.day);
}
export function apply(state, command, now=new Date().toISOString(), {reconcile=true}={}) {
 timestamp(now); const s=clone(state); const values=command.values||{};
 if(reconcile)reconcileCalendar(s,now);
 // Focus records without kind are pre-upgrade timers: finish under their original accounting contract.
 if(s.focus && timestamp(now)>=timestamp(s.focus.ends_at)) {
 finishFocus(s,s.focus.ends_at);
 }
 if(command.type==='stopFocus') {finishFocus(s,now);return s;}
 if(command.type==='dismissFocusResume'){s.focusResumeTaskId=null;return s;}
 if(command.type==='resumeFocusTask'){
 const previous=s.tasks.find(t=>t.id===s.focusResumeTaskId&&t.status!=='completed');
 if(!previous)fail('Задача для продолжения недоступна');start(s,previous,now);if(!previous.planned_days.includes(localDay(now)))previous.planned_days.push(localDay(now));s.focusResumeTaskId=null;return s;
 }
 if(command.type==='replaceState')return validateBackup(values);
 if(command.type==='createTask') {
 const task={id:id(),title:'',description:'',day:localDay(now),priority:4,status:'open',sessions:[],created_at:now,completed_at:null,continuation_of:null,bitrix:null,planned_days:[],daily_priorities:{},keep_priority:false,result:''};
 taskFields(values,task,now); if(!task.title)fail('Введите название задачи'); task.planned_days=[task.day];s.tasks.push(task); return s;
 }
 if(command.type==='assignPriority'){
 const day=calendar(values.day);if(!Number.isInteger(values.priority)||values.priority<1||values.priority>4)fail('Приоритет должен быть от 1 до 4');
 if(!Array.isArray(command.taskIds))fail('Выберите задачи');
 for(const taskId of new Set(command.taskIds)){const task=s.tasks.find(t=>t.id===taskId);if(!task)fail('Задача не найдена');task.daily_priorities[day]=values.priority;if(values.priority!==4&&!task.planned_days.includes(day))task.planned_days.push(day);task.priority=priorityFor(task,task.day);}
 return s;
 }
 if(command.type==='reconcile')return s;
 if(command.type==='startFocus') {
 if(s.focus)fail('Сначала остановите текущую концентрацию');
 if(!Number.isInteger(values.minutes)||values.minutes<1||values.minutes>180)fail('Длительность должна быть целым числом от 1 до 180 минут');
 const previous=s.tasks.find(t=>active(t))||s.tasks.filter(t=>t.status==='paused'&&t.sessions.length).sort((a,b)=>Date.parse(b.sessions.at(-1).ended_at||b.sessions.at(-1).started_at)-Date.parse(a.sessions.at(-1).ended_at||a.sessions.at(-1).started_at))[0];
 if(previous)close(previous,now);
 const date=new Date(now),pad=n=>String(n).padStart(2,'0');
 const title='Концентрация · '+values.minutes+' мин · '+pad(date.getDate())+'.'+pad(date.getMonth()+1)+'.'+date.getFullYear()+' '+pad(date.getHours())+':'+pad(date.getMinutes());
 const created=apply(s,{type:'createTask',values:{title,description:'Режим концентрации'}},now,{reconcile:false});
 const task=created.tasks.at(-1);start(created,task,now);
 created.focus={kind:'desktop',taskId:task.id,previousTaskId:previous?.id??null,started_at:now,ends_at:new Date(timestamp(now)+values.minutes*60000).toISOString()};
 created.focusResumeTaskId=null;return created;
 }
 const task=s.tasks.find(t=>t.id===command.taskId); if(!task)fail('Задача не найдена');
 switch(command.type) {
 case 'addToPlan':{const day=calendar(values.day);if(!task.planned_days.includes(day))task.planned_days.push(day);task.daily_priorities[day]=values.priority??priorityFor(task,day);if(!Number.isInteger(task.daily_priorities[day])||task.daily_priorities[day]<1||task.daily_priorities[day]>4)fail('Приоритет должен быть от 1 до 4');task.priority=priorityFor(task,task.day);break;}
 case 'removeFromPlan':{const day=calendar(values.day);task.planned_days=task.planned_days.filter(d=>d!==day);delete task.daily_priorities[day];task.priority=priorityFor(task,task.day);break;}
 case 'addSession': {
 const entry={id:id(),started_at:values.started_at,ended_at:values.ended_at,comment:values.comment??'',bitrix_record_id:null};
 checkSession(entry,true);task.sessions.push(entry);break;
 }
 case 'updateSession': {
 const entry=task.sessions.find(e=>e.id===command.sessionId);if(!entry)fail('Сессия не найдена');
 const wasActive=entry.ended_at===null;
 const unchangedTimes=(!('started_at' in values)||values.started_at===entry.started_at)&&(!('ended_at' in values)||values.ended_at===entry.ended_at);
 for(const key of ['started_at','ended_at','comment'])if(key in values)entry[key]=values[key];
 if(!wasActive && entry.ended_at===null)fail('Закрытую сессию нельзя открыть');
 if(unchangedTimes){if(typeof entry.comment!=='string')fail('Комментарий должен быть текстом');}else checkSession(entry,false);
 if(wasActive && entry.ended_at!==null){task.status='paused';if(s.focus?.taskId===task.id)finishFocus(s,entry.ended_at);}
 if(wasActive && entry.ended_at===null && timestamp(entry.started_at)>timestamp(now))fail('Активная сессия не может начинаться в будущем');
 if(wasActive && entry.ended_at===null && s.focus?.taskId===task.id && timestamp(entry.started_at)>timestamp(s.focus.started_at))fail('Начало сессии не может быть позже начала концентрации. Сначала остановите концентрацию.');
 break;
 }
 case 'deleteSession': {
 const entry=task.sessions.find(e=>e.id===command.sessionId);if(!entry)fail('Сессия не найдена');
 task.sessions=task.sessions.filter(e=>e.id!==command.sessionId);
 if(entry.ended_at===null){task.status='paused';if(s.focus?.taskId===task.id)finishFocus(s,now);}break;
 }
 case 'updateTask':taskFields(values,task,now);break;
 case 'startTask':start(s,task,now);s.focusResumeTaskId=null;if(!task.planned_days.includes(localDay(now)))task.planned_days.push(localDay(now));break;
 case 'pauseTask':if(s.focus?.taskId===task.id)finishFocus(s,now);else close(task,now);break;
 case 'completeTask':if('result' in values)taskFields({result:values.result},task,now);close(task,now);task.status='completed';task.completed_at=now;if(s.focus?.taskId===task.id)finishFocus(s,now);break;
 case 'deleteTask':if(s.focus?.taskId===task.id)finishFocus(s,now);s.tasks=s.tasks.filter(t=>t.id!==task.id);if(s.focusResumeTaskId===task.id)s.focusResumeTaskId=null;break;
 default:fail('Неизвестная операция');
 }
 return s;
}
function checkSession(entry, requireEnd) {
 timestamp(entry.started_at);
 if(entry.ended_at===null && !requireEnd) {} else {
 if(timestamp(entry.ended_at)<=timestamp(entry.started_at))fail('Окончание должно быть позже начала');
 }
 if(typeof entry.comment!=='string')fail('Комментарий должен быть текстом');
}
export function validateBackup(value, {allowMultipleActive=false} = {}) {
 const object=v=>v!==null && typeof v==='object' && !Array.isArray(v);
 if(!object(value)||value.schemaVersion!==1||!Array.isArray(value.tasks)||!('focus' in value))fail('Неподдерживаемый формат резервной копии');
 const ids=new Set();let running=0;
 for(const task of value.tasks) {
 if(!object(task)||typeof task.id!=='string'||!task.id||ids.has(task.id))fail('Некорректный или повторяющийся идентификатор задачи');ids.add(task.id);
 if(typeof task.title!=='string'||!task.title.trim()||typeof task.description!=='string')fail('Некорректные поля задачи');
 calendar(task.day);timestamp(task.created_at);
 if('planned_days'in task){if(!Array.isArray(task.planned_days))fail('Некорректный план задачи');for(const day of task.planned_days)calendar(day);}
 if('daily_priorities'in task){if(!object(task.daily_priorities))fail('Некорректные дневные приоритеты');for(const [day,p] of Object.entries(task.daily_priorities)){calendar(day);if(!Number.isInteger(p)||p<1||p>4)fail('Некорректный дневной приоритет');}}
 if('result'in task&&typeof task.result!=='string')fail('Результат должен быть текстом');
 if('keep_priority'in task&&typeof task.keep_priority!=='boolean')fail('Некорректное сохранение приоритета');
 if(!Number.isInteger(task.priority)||task.priority<1||task.priority>4||!['open','running','paused','completed'].includes(task.status)||!Array.isArray(task.sessions))fail('Некорректное состояние задачи');
 if(task.completed_at!==null)timestamp(task.completed_at);
 let opened=0;const sessionIds=new Set();
 for(const entry of task.sessions) {
 if(!object(entry)||typeof entry.id!=='string'||!entry.id||sessionIds.has(entry.id))fail('Некорректный или повторяющийся идентификатор сессии');sessionIds.add(entry.id);
 timestamp(entry.started_at);
 if(entry.ended_at===null)opened++;else if(timestamp(entry.ended_at)<timestamp(entry.started_at))fail('Окончание сессии раньше начала');
 if(typeof entry.comment!=='string'||!(entry.bitrix_record_id===null||typeof entry.bitrix_record_id==='string'))fail('Некорректные поля сессии');
 }
 if((opened>1&&!allowMultipleActive)||(task.status==='running')!==(opened>=1))fail('Статус задачи не соответствует активной сессии');running+=opened;
 }
 if(running>1&&!allowMultipleActive)fail('В копии несколько активных задач');
 if('plan_rollover_day'in value)calendar(value.plan_rollover_day);
 if('focusResumeTaskId'in value&&value.focusResumeTaskId!==null&&typeof value.focusResumeTaskId!=='string')fail('Некорректная задача для продолжения');
 if(value.focus!==null) {
 const f=value.focus;if(!object(f))fail('Некорректная концентрация');
 if('kind'in f&&f.kind!=='desktop')fail('Некорректный режим концентрации');
 if(f.kind==='desktop'&&(typeof f.taskId!=='string'||!(f.previousTaskId===null||typeof f.previousTaskId==='string')))fail('Некорректная задача концентрации');
 const task=value.tasks.find(t=>t.id===f.taskId);
 if(f.taskId!==null&&(!task||!active(task)||timestamp(active(task).started_at)>timestamp(f.started_at)))fail('Концентрация не соответствует активной задаче');
 const duration=timestamp(f.ends_at)-timestamp(f.started_at);if(duration<60000||duration>10800000||duration%60000!==0)fail('Некорректная длительность концентрации');
 }
 // Only JSON snapshots are accepted; additional JSON metadata is retained unchanged.
 let copy;try{copy=JSON.parse(JSON.stringify(value));}catch{fail('Резервная копия должна содержать JSON');}
 return copy;
}
export function sessionSeconds(session, now=new Date().toISOString()) {return Math.max(0,Math.floor((timestamp(session.ended_at ?? now)-timestamp(session.started_at))/1000));}
export function totalSeconds(task, now=new Date().toISOString()) {return task.sessions.reduce((sum,s)=>sum+sessionSeconds(s,now),0);}
