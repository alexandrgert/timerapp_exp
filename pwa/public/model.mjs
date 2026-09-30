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
 if('day' in values) task.day=calendar(values.day);
 if('priority' in values) {if(!Number.isInteger(values.priority)||values.priority<1||values.priority>4) fail('Приоритет должен быть от 1 до 4'); task.priority=values.priority;}
}
function close(task, now) { const session=active(task); if(session) {if(timestamp(now)<timestamp(session.started_at)) fail('Время окончания раньше начала сессии'); session.ended_at=now;} if(task.status==='running')task.status='paused'; }
function start(state, task, now) {
 if(task.status==='completed') fail('Завершённую задачу нельзя запустить');
 if(active(task)){if(timestamp(active(task).started_at)>timestamp(now))fail('Текущее время раньше начала сессии. Проверьте часы устройства или исправьте сессию.');return;}
 for(const other of state.tasks)if(other!==task && active(other))close(other,now);
 if(state.focus && state.focus.taskId!==task.id)state.focus=null;
 task.sessions.push({id:id(),started_at:now,ended_at:null,comment:'',bitrix_record_id:null}); task.status='running';
}
export function apply(state, command, now=new Date().toISOString()) {
 timestamp(now); const s=clone(state); const values=command.values||{};
 if(s.focus && timestamp(now)>=timestamp(s.focus.ends_at)) {
 const focused=s.tasks.find(t=>t.id===s.focus.taskId);if(focused)close(focused,s.focus.ends_at);s.focus=null;
 }
 if(command.type==='stopFocus') {if(s.focus){const focused=s.tasks.find(t=>t.id===s.focus.taskId);if(focused)close(focused,now);s.focus=null;}return s;}
 if(command.type==='replaceState')return validateBackup(values);
 if(command.type==='createTask') {
 const task={id:id(),title:'',description:'',day:now.slice(0,10),priority:4,status:'open',sessions:[],created_at:now,completed_at:null,continuation_of:null,bitrix:null,planned_days:[],daily_priorities:{},keep_priority:false,result:''};
 taskFields(values,task,now); if(!task.title)fail('Введите название задачи'); s.tasks.push(task); return s;
 }
 if(command.type==='reconcile')return s;
 const task=s.tasks.find(t=>t.id===command.taskId); if(!task)fail('Задача не найдена');
 switch(command.type) {
 case 'startFocus': {
 if(s.focus)fail('Сначала остановите текущую концентрацию');
 if(!Number.isInteger(values.minutes)||values.minutes<1||values.minutes>180)fail('Длительность должна быть целым числом от 1 до 180 минут');
 start(s,task,now);s.focus={taskId:task.id,started_at:now,ends_at:new Date(timestamp(now)+values.minutes*60000).toISOString()};break;
 }
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
 if(wasActive && entry.ended_at!==null){task.status='paused';if(s.focus?.taskId===task.id)s.focus=null;}
 if(wasActive && entry.ended_at===null && timestamp(entry.started_at)>timestamp(now))fail('Активная сессия не может начинаться в будущем');
 if(wasActive && entry.ended_at===null && s.focus?.taskId===task.id && timestamp(entry.started_at)>timestamp(s.focus.started_at))fail('Начало сессии не может быть позже начала концентрации. Сначала остановите концентрацию.');
 break;
 }
 case 'deleteSession': {
 const entry=task.sessions.find(e=>e.id===command.sessionId);if(!entry)fail('Сессия не найдена');
 task.sessions=task.sessions.filter(e=>e.id!==command.sessionId);
 if(entry.ended_at===null){task.status='paused';if(s.focus?.taskId===task.id)s.focus=null;}break;
 }
 case 'updateTask':taskFields(values,task,now);break;
 case 'startTask':start(s,task,now);break;
 case 'pauseTask':close(task,now); if(s.focus?.taskId===task.id)s.focus=null;break;
 case 'completeTask':close(task,now);task.status='completed';task.completed_at=now;if(s.focus?.taskId===task.id)s.focus=null;break;
 case 'deleteTask':s.tasks=s.tasks.filter(t=>t.id!==task.id);if(s.focus?.taskId===task.id)s.focus=null;break;
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
export function validateBackup(value) {
 const object=v=>v!==null && typeof v==='object' && !Array.isArray(v);
 if(!object(value)||value.schemaVersion!==1||!Array.isArray(value.tasks)||!('focus' in value))fail('Неподдерживаемый формат резервной копии');
 const ids=new Set();let running=0;
 for(const task of value.tasks) {
 if(!object(task)||typeof task.id!=='string'||!task.id||ids.has(task.id))fail('Некорректный или повторяющийся идентификатор задачи');ids.add(task.id);
 if(typeof task.title!=='string'||!task.title.trim()||typeof task.description!=='string')fail('Некорректные поля задачи');
 calendar(task.day);timestamp(task.created_at);
 if(!Number.isInteger(task.priority)||task.priority<1||task.priority>4||!['open','running','paused','completed'].includes(task.status)||!Array.isArray(task.sessions))fail('Некорректное состояние задачи');
 if(task.completed_at!==null)timestamp(task.completed_at);
 let opened=0;const sessionIds=new Set();
 for(const entry of task.sessions) {
 if(!object(entry)||typeof entry.id!=='string'||!entry.id||sessionIds.has(entry.id))fail('Некорректный или повторяющийся идентификатор сессии');sessionIds.add(entry.id);
 timestamp(entry.started_at);
 if(entry.ended_at===null)opened++;else if(timestamp(entry.ended_at)<timestamp(entry.started_at))fail('Окончание сессии раньше начала');
 if(typeof entry.comment!=='string'||!(entry.bitrix_record_id===null||typeof entry.bitrix_record_id==='string'))fail('Некорректные поля сессии');
 }
 if(opened>1||(task.status==='running')!==(opened===1))fail('Статус задачи не соответствует активной сессии');running+=opened;
 }
 if(running>1)fail('В копии несколько активных задач');
 if(value.focus!==null) {
 const f=value.focus;if(!object(f))fail('Некорректная концентрация');
 const task=value.tasks.find(t=>t.id===f.taskId);
 if(!task||!active(task)||timestamp(f.ends_at)<=timestamp(f.started_at)||timestamp(active(task).started_at)>timestamp(f.started_at))fail('Концентрация не соответствует активной задаче');
 const duration=timestamp(f.ends_at)-timestamp(f.started_at);if(duration<60000||duration>10800000||duration%60000!==0)fail('Некорректная длительность концентрации');
 }
 // Only JSON snapshots are accepted; additional JSON metadata is retained unchanged.
 let copy;try{copy=JSON.parse(JSON.stringify(value));}catch{fail('Резервная копия должна содержать JSON');}
 return copy;
}
export function sessionSeconds(session, now=new Date().toISOString()) {return Math.max(0,Math.floor((timestamp(session.ended_at ?? now)-timestamp(session.started_at))/1000));}
export function totalSeconds(task, now=new Date().toISOString()) {return task.sessions.reduce((sum,s)=>sum+sessionSeconds(s,now),0);}
