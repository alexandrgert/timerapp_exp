// Language-neutral causal operation log. See docs/sync-v2.md.
const fail=m=>{throw new Error(m);};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const own=(v,k)=>Object.prototype.hasOwnProperty.call(v,k);
const unicodeOK=s=>!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(s);
const order=(a,b)=>{const x=Array.from(a),y=Array.from(b);for(let i=0;i<Math.min(x.length,y.length);i++){const d=x[i].codePointAt(0)-y[i].codePointAt(0);if(d)return d;}return x.length-y.length;};
const MAX_OPS=20000, MAX_BYTES=20*1024*1024;
export const emptyDocument=()=>({format:'tasktimer-sync',version:2,ops:[]});
export function canonical(value){
 if(typeof value==='string'&&!unicodeOK(value))fail('Некорректный Unicode');
 if(value===null||typeof value==='boolean'||typeof value==='string')return JSON.stringify(value);
 if(typeof value==='number'&&Number.isFinite(value))return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(object(value))return '{'+Object.keys(value).sort(order).map(k=>{if(!unicodeOK(k))fail('Некорректный Unicode');return JSON.stringify(k)+':'+canonical(value[k]);}).join(',')+'}';
 fail('Протокол синхронизации принимает только JSON');
}
const copy=v=>JSON.parse(canonical(v));
const dot=o=>canonical([o.actor,o.seq]);
const key=e=>canonical(e);
const actorOK=a=>typeof a==='string'&&/^[A-Za-z0-9_.:-]{1,160}$/.test(a)&&!['__proto__','constructor','prototype'].includes(a);
const entityOK=e=>Array.isArray(e)&&((e[0]==='task'&&e.length===2)||(e[0]==='session'&&e.length===3))&&e.slice(1).every(x=>typeof x==='string'&&x.length>0&&x.length<=512);
export function validateDocument(doc){
 if(!object(doc)||doc.format!=='tasktimer-sync'||doc.version!==2||!Array.isArray(doc.ops))fail('Неподдерживаемый формат синхронизации');
 if(doc.ops.length>MAX_OPS||new TextEncoder().encode(canonical(doc)).length>MAX_BYTES)fail('Журнал синхронизации превышает безопасный размер; данные не изменены');
 const ids=new Set(),counts=new Map();
 for(const op of doc.ops){
  if(!object(op)||!actorOK(op.actor)||!Number.isSafeInteger(op.seq)||op.seq<1||!object(op.seen)||!entityOK(op.entity)||!object(op.changes)||!Object.keys(op.changes).length)fail('Некорректная операция синхронизации');
  for(const [a,n] of Object.entries(op.seen))if(!actorOK(a)||!Number.isSafeInteger(n)||n<1)fail('Некорректная причинная версия');
  if((op.seen[op.actor]??0)!==op.seq-1)fail('Разрыв последовательности устройства');
  if(own(op.changes,'$alive')&&typeof op.changes.$alive!=='boolean')fail('Некорректная отметка существования записи');
  if(Object.keys(op.changes).some(k=>k==='id'||k==='sessions'||k==='__proto__'||k==='constructor'||k==='prototype'))fail('Зарезервированное поле синхронизации');
  if(op.entity[0]==='session'&&own(op.changes,'interval')&&(!object(op.changes.interval)||Object.keys(op.changes.interval).some(k=>!['started_at','ended_at','duration_seconds'].includes(k))))fail('Некорректный интервал сессии');
  if(ids.has(dot(op)))fail('Повтор идентификатора операции');ids.add(dot(op));
  if(!counts.has(op.actor))counts.set(op.actor,new Set());counts.get(op.actor).add(op.seq);
 }
 for(const seqs of counts.values())if(seqs.size!==Math.max(...seqs))fail('Неполный журнал устройства');
 for(const op of doc.ops)for(const [a,n] of Object.entries(op.seen))if(!counts.get(a)?.has(n))fail('Отсутствует причинный предшественник');
 // Context must include the context of every referenced predecessor; reject cycles.
 const byId=new Map(doc.ops.map(o=>[dot(o),o]));
 for(const op of doc.ops)for(const [a,n] of Object.entries(op.seen)){
  const prev=byId.get(canonical([a,n]));
  if((prev.seen[op.actor]??0)>=op.seq)fail('Цикл причинных версий');
  for(const [b,m] of Object.entries(prev.seen))if((op.seen[b]??0)<m)fail('Неполный причинный контекст');
 }
 return copy(doc);
}
export function mergeDocuments(a,b){
 a=validateDocument(a);b=validateDocument(b);
 const ops=new Map(a.ops.map(o=>[dot(o),o]));
 for(const op of b.ops){const old=ops.get(dot(op));if(old&&canonical(old)!==canonical(op))fail('Коллизия идентификатора устройства: синхронизация остановлена');ops.set(dot(op),op);}
 // Unknown top-level extension values must agree; never silently discard them.
 const result={...a};for(const [k,v] of Object.entries(b))if(k!=='ops'){if(own(result,k)&&canonical(result[k])!==canonical(v))fail('Конфликт расширения формата');Object.defineProperty(result,k,{value:v,enumerable:true,writable:true,configurable:true});}
 result.ops=[...ops.values()].sort((x,y)=>dot(x)<dot(y)?-1:dot(x)>dot(y)?1:0);
 return validateDocument(result);
}
function appendChange(doc,actor,entity,changes){
 if(!actorOK(actor)||!entityOK(entity)||!object(changes))fail('Некорректная правка');
 const seen=Object.create(null);for(const o of doc.ops)seen[o.actor]=Math.max(seen[o.actor]??0,o.seq);
 doc.ops.push({actor,seq:(seen[actor]??0)+1,seen,entity:copy(entity),changes:{$alive:true,...copy(changes)}});
 if(entity[0]==='session')appendChange(doc,actor,['task',entity[1]],{$alive:true});
}
export function changeEntity(doc,actor,entity,changes){
 doc=validateDocument(doc);appendChange(doc,actor,entity,changes);return validateDocument(doc);
}
export function projectDocument(doc){
 doc=validateDocument(doc);const entities=[],conflicts=[];
 const groups=new Map();for(const o of doc.ops){const k=key(o.entity);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(o);}
 for(const entityKey of [...groups.keys()].sort(order)){
  const ops=groups.get(entityKey),entity=JSON.parse(entityKey),values=Object.create(null);
  for(const field of [...new Set(ops.flatMap(o=>Object.keys(o.changes)))].sort(order)){
   const writes=ops.filter(o=>own(o.changes,field));
   const observed=Object.create(null);for(const p of writes)for(const [a,n] of Object.entries(p.seen))observed[a]=Math.max(observed[a]??0,n);
   const maximal=writes.filter(o=>(observed[o.actor]??0)<o.seq);
   const variants=new Map();for(const o of maximal){const v=canonical(o.changes[field]);if(!variants.has(v))variants.set(v,{value:copy(o.changes[field]),dots:[]});variants.get(v).dots.push([o.actor,o.seq]);}
   const candidates=[...variants.values()].map(v=>({...v,dots:v.dots.sort((a,b)=>order(canonical(a),canonical(b)))})).sort((a,b)=>order(canonical(a.dots[0]),canonical(b.dots[0])));
   if(candidates.length>1)conflicts.push({entity,field,candidates});
   values[field]=candidates[0].value;
   // Delete wins projection only. Both alternatives remain available to resolve.
   if(field==='$alive'&&candidates.some(v=>v.value===false))values[field]=false;
  }
  entities.push({entity,deleted:values.$alive===false,values});
 }
 return {entities,conflicts};
}
export function resolveConflict(doc,actor,entity,field,value){
 const conflict=projectDocument(doc).conflicts.find(c=>key(c.entity)===key(entity)&&c.field===field);
 if(!conflict)fail('Конфликт уже изменился; обновите список');
 if(!conflict.candidates.some(c=>canonical(c.value)===canonical(value)))fail('Выберите сохранённый вариант');
 doc=validateDocument(doc);if(!actorOK(actor))fail('Некорректное устройство');
 const seen=Object.create(null);for(const o of doc.ops)seen[o.actor]=Math.max(seen[o.actor]??0,o.seq);
 doc.ops.push({actor,seq:(seen[actor]??0)+1,seen,entity:copy(entity),changes:{[field]:copy(value)}});
 return validateDocument(doc);
}
function flattenTasks(tasks){
 if(!Array.isArray(tasks))fail('Ожидался список задач');const result=new Map();
 for(const task of tasks){
  const e=['task',task.id];if(!entityOK(e)||result.has(key(e))||!Array.isArray(task.sessions))fail('Некорректная задача');
  const values=copy(task);delete values.id;delete values.sessions;result.set(key(e),values);
  for(const session of task.sessions){
   const se=['session',task.id,session.id];if(!entityOK(se)||result.has(key(se)))fail('Некорректная сессия');
   const sv=copy(session);delete sv.id;const interval={};
   for(const f of ['started_at','ended_at','duration_seconds'])if(own(sv,f)){interval[f]=sv[f];delete sv[f];}
   sv.interval=interval;result.set(key(se),sv);
  }
 }
 return result;
}
export function importLegacy(tasks,actor){return reconcileTasks(emptyDocument(),[],tasks,actor);}
export function reconcileTasks(doc,beforeTasks,afterTasks,actor){
 const before=flattenTasks(beforeTasks),after=flattenTasks(afterTasks);doc=validateDocument(doc);
 // Tasks first, then sessions; parent touches communicate session edits to task deletion.
 const keys=[...new Set([...before.keys(),...after.keys()])].sort((a,b)=>JSON.parse(a)[0]===JSON.parse(b)[0]?(a<b?-1:1):(JSON.parse(a)[0]==='task'?-1:1));
 for(const k of keys){
  const old=before.get(k),next=after.get(k),entity=JSON.parse(k);
  if(!next){if(entity[0]==='session'&&!after.has(key(['task',entity[1]])))continue;appendChange(doc,actor,entity,{$alive:false});continue;}
  const changes=Object.create(null);
  for(const field of Object.keys(next))if(!old||!own(old,field)||canonical(old[field])!==canonical(next[field]))changes[field]=next[field];
  // Missing optional fields are explicit nulls; unknown metadata is never erased merely
  // because an older adapter omitted it. Only fields present in after are written.
  if(Object.keys(changes).length)appendChange(doc,actor,entity,changes);
 }
 return validateDocument(doc);
}
export function projectTasks(doc){
 const {entities,conflicts}=projectDocument(doc),tasks=[];
 for(const e of entities.filter(e=>e.entity[0]==='task'&&!e.deleted)){
  const task={...copy(e.values),id:e.entity[1],sessions:[]};delete task.$alive;
  // Parent-only causal touches can precede task creation; no incomplete task is exposed.
  if(!own(task,'title'))continue;
  for(const s of entities.filter(s=>s.entity[0]==='session'&&s.entity[1]===task.id&&!s.deleted)){
   const session={...copy(s.values),id:s.entity[2]};delete session.$alive;
   const interval=session.interval;delete session.interval;Object.assign(session,interval);task.sessions.push(session);
  }
  tasks.push(task);
 }
 return {tasks,conflicts};
}
export function remoteV2Path(path){
 if(typeof path!=='string'||!path||/[?#]/.test(path))fail('Некорректный путь WebDAV');
 return path+'.v2.json';
}
