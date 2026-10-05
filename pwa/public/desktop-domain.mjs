export function localDay(value=new Date()) {
 const d=new Date(value),pad=n=>String(n).padStart(2,'0');
 return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
}
export function priorityFor(task,day) {const p=task.daily_priorities?.[day];return Number.isInteger(p)&&p>=1&&p<=4?p:4;}
const duration=(session,now)=>Math.max(0,Math.floor((Date.parse(session.ended_at??now)-Date.parse(session.started_at))/1000));
export function secondsOnDay(task,day,now=new Date().toISOString()) {return task.sessions.filter(s=>localDay(s.started_at)===day).reduce((sum,s)=>sum+duration(s,now),0);}
const running=task=>task.sessions.some(s=>s.ended_at===null);
export function visibleTasks(state,{view='today',day=localDay(),query='',priorities=[]}={},now=new Date().toISOString()){
 const levels=new Set(priorities),needle=query.trim().toLocaleLowerCase();
 let tasks=state.tasks.filter(task=>{
 if(needle&&!task.title.toLocaleLowerCase().includes(needle))return false;
 if(view==='today'&&!(task.planned_days?.includes(day)&&(task.day===day||running(task)||Object.hasOwn(task.daily_priorities||{},day))))return false;
 if(view==='progress'&&task.status==='completed')return false;
 if(view==='date'&&secondsOnDay(task,day,now)<=0)return false;
 return !levels.size||levels.has(priorityFor(task,day))||(view==='today'&&running(task));
 });
 if(view==='today')return tasks.sort((a,b)=>Number(running(b))-Number(running(a))||Number(a.status==='completed')-Number(b.status==='completed')||priorityFor(a,day)-priorityFor(b,day)||a.created_at.localeCompare(b.created_at));
 return tasks.sort((a,b)=>Number(running(b))-Number(running(a))||b.created_at.localeCompare(a.created_at));
}
const hm=seconds=>String(Math.floor(seconds/3600)).padStart(2,'0')+':'+String(Math.floor(seconds/60)%60).padStart(2,'0');
const dayLabel=day=>day.split('-').reverse().join('.');
function dateLabel(value){const d=new Date(value);return dayLabel(localDay(d))+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}
export function buildDayReport(state,day,{extended=false,now=new Date().toISOString()}={}){
 const tasks=state.tasks.filter(t=>secondsOnDay(t,day,now)>0).sort((a,b)=>secondsOnDay(b,day,now)-secondsOnDay(a,day,now));
 const label=dayLabel(day);if(!tasks.length)return '# Отчёт за '+label+'\n\nЗа '+label+' время не учтено.';
 const lines=['# Отчёт за '+label,'','**Итого:** '+hm(tasks.reduce((n,t)=>n+secondsOnDay(t,day,now),0)),''];
 tasks.forEach((task,index)=>{
 if(index)lines.push('');lines.push('## '+task.title+' — '+hm(secondsOnDay(task,day,now)));
 if(task.result?.trim())lines.push('','**Результат:** '+task.result.trim());
 if(!extended)return;
 if(task.description.trim())lines.push('','### Описание',task.description.trim());
 const sessions=task.sessions.filter(s=>localDay(s.started_at)===day);
 if(sessions.length)lines.push('','### Сессии за день','| Начало | Окончание | Длительность | Комментарий | Передано |','| --- | --- | --- | --- | --- |');
 const cell=value=>String(value??'').replaceAll('|','\\|').replaceAll('\n',' ');
 for(const session of sessions)lines.push('| '+[dateLabel(session.started_at),session.ended_at?dateLabel(session.ended_at):'идёт',hm(duration(session,now)),cell(session.comment),cell(session.bitrix_record_id)].join(' | ')+' |');
 });
 return lines.join('\n');
}
