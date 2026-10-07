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
 const ranks=new Map((state.taskOrder||[]).map((id,i)=>[id,i]));
 return tasks.sort((a,b)=>{
 const pinned=Number(running(b))-Number(running(a));if(pinned)return pinned;
 const completed=Number(a.status==='completed')-Number(b.status==='completed');if(completed)return completed;
 if(a.status==='completed')return Date.parse(a.completed_at||a.created_at)-Date.parse(b.completed_at||b.created_at)||a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id);
 if(ranks.size)return (ranks.get(a.id)??Infinity)-(ranks.get(b.id)??Infinity)||b.created_at.localeCompare(a.created_at)||a.id.localeCompare(b.id);
 return view==='today'?priorityFor(a,day)-priorityFor(b,day)||a.created_at.localeCompare(b.created_at):b.created_at.localeCompare(a.created_at);
 });
}
const hm=seconds=>String(Math.floor(seconds/3600)).padStart(2,'0')+':'+String(Math.floor(seconds/60)%60).padStart(2,'0');
const dayLabel=day=>day.split('-').reverse().join('.');
function dateLabel(value){const d=new Date(value);return dayLabel(localDay(d))+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}
// One snapshot is shared by Markdown and the table, including running sessions.
export function dayReportData(state,day,{now=new Date().toISOString()}={}){
 const tasks=state.tasks.map(task=>({
  title:task.title,result:task.result?.trim()||'',description:task.description.trim(),
  concentration:task.title.startsWith('Концентрация · ')&&task.description==='Режим концентрации',
  seconds:secondsOnDay(task,day,now),
  sessions:task.sessions.filter(s=>localDay(s.started_at)===day).map(s=>({
   start:dateLabel(s.started_at),end:s.ended_at?dateLabel(s.ended_at):'идёт',
   elapsed:hm(duration(s,now)),comment:s.comment||'',transferred:String(s.bitrix_record_id??'')
  }))
 })).filter(t=>t.seconds>0).sort((a,b)=>b.seconds-a.seconds);
 return {day,label:dayLabel(day),total:hm(tasks.reduce((n,t)=>n+t.seconds,0)),tasks:tasks.map(t=>({...t,elapsed:hm(t.seconds)}))};
}
export function formatDayReport(report,{extended=false}={}){
 const {tasks,label}=report;if(!tasks.length)return '# Отчёт за '+label+'\n\nЗа '+label+' время не учтено.';
 const lines=['# Отчёт за '+label,'','**Итого:** '+report.total,''];
 tasks.forEach((task,index)=>{
 if(index)lines.push('');lines.push('## '+task.title+' — '+task.elapsed);
 if(task.result)lines.push('','**Результат:** '+task.result);
 if(!extended)return;
 if(task.description)lines.push('','### Описание',task.description);
 if(task.sessions.length)lines.push('','### Сессии за день','| Начало | Окончание | Длительность | Комментарий | Передано |','| --- | --- | --- | --- | --- |');
 const cell=value=>String(value??'').replaceAll('|','\\|').replaceAll('\n',' ');
 for(const session of task.sessions)lines.push('| '+[session.start,session.end,session.elapsed,cell(session.comment),cell(session.transferred)].join(' | ')+' |');
 });
 return lines.join('\n');
}
export function buildDayReport(state,day,options={}){return formatDayReport(dayReportData(state,day,options),options);}
