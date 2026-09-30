import {test} from 'node:test';
import assert from 'node:assert/strict';
import {emptyDocument,changeEntity,mergeDocuments,projectDocument} from '../public/sync-protocol.mjs';
test('causal shorter duration and cleared comment survive stale copies',()=>{
 const initial=changeEntity(emptyDocument(),'a',['session','t','s'],{interval:{started_at:'2026-01-01T10:00:00Z',ended_at:'2026-01-01T11:00:00Z'},comment:'old'});
 const edit=changeEntity(initial,'a',['session','t','s'],{interval:{started_at:'2026-01-01T10:00:00Z',ended_at:'2026-01-01T10:40:00Z'},comment:''});
 const projected=projectDocument(mergeDocuments(initial,edit));
 const s=projected.entities.find(e=>e.entity[0]==='session').values;
 assert.equal(s.interval.ended_at,'2026-01-01T10:40:00Z');assert.equal(s.comment,'');assert.equal(projected.conflicts.length,0);
});
test('task adapters retain metadata and produce session tombstones',async()=>{
 const {importLegacy,reconcileTasks,projectTasks}=await import('../public/sync-protocol.mjs');
 const tasks=[{id:'t',title:'A',extension:{n:1},sessions:[{id:'s',started_at:'a',ended_at:'b',duration_seconds:60,comment:'old'}]}];
 const initial=importLegacy(tasks,'legacy-a');
 assert.deepEqual(projectTasks(initial).tasks,tasks);
 const after=[{...tasks[0],sessions:[]}];
 const changed=reconcileTasks(initial,tasks,after,'a');
 assert.deepEqual(projectTasks(mergeDocuments(changed,initial)).tasks,after);
});
test('shared fixture semantics and convergence under repeat, permutation and grouping',async()=>{
 const fs=await import('node:fs');const cases=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/sync-v2/cases.json',import.meta.url)));
 for(const c of cases){
  const merged=mergeDocuments(c.left,c.right);assert.deepEqual(merged,mergeDocuments(c.right,c.left),c.name);
  assert.deepEqual(merged,mergeDocuments(merged,merged),c.name);
  assert.deepEqual(mergeDocuments(mergeDocuments(c.left,c.right),emptyDocument()),mergeDocuments(c.left,mergeDocuments(c.right,emptyDocument())),c.name);
  const p=projectDocument(merged),t=p.entities.find(e=>JSON.stringify(e.entity)===JSON.stringify(c.entity??['task','t']));
  for(const [field,v] of Object.entries(c.expectedFields??{}))assert.deepEqual(t.values[field],v,c.name);
  if('expectedDeleted'in c)assert.equal(t.deleted,c.expectedDeleted,c.name);
  assert.deepEqual(p.conflicts.map(c=>c.field).sort(),c.expectedConflictFields,c.name);
 }
});
test('resolving one field retains concurrent deletion and resolving lifecycle restores explicitly',async()=>{
 const {resolveConflict}=await import('../public/sync-protocol.mjs');
 const base=changeEntity(emptyDocument(),'seed',['task','t'],{title:'Original'});
 const a=changeEntity(base,'a',['task','t'],{title:'A'}), b=changeEntity(base,'b',['task','t'],{title:'B'}), del=changeEntity(base,'c',['task','t'],{$alive:false});
 const merged=mergeDocuments(mergeDocuments(a,b),del);
 const resolved=resolveConflict(merged,'a',['task','t'],'title','B');
 assert.equal(projectDocument(resolved).entities[0].deleted,true);
 assert.equal(projectDocument(resolved).entities[0].values.title,'B');
 assert.deepEqual(projectDocument(resolved).conflicts.map(c=>c.field),['$alive']);
 const restored=resolveConflict(merged,'a',['task','t'],'$alive',true);
 assert.equal(projectDocument(restored).entities[0].deleted,false);
 assert.equal(projectDocument(restored).conflicts[0].field,'title');
});
test('independent legacy migration retains ambiguous values against tombstones',async()=>{
 const {importLegacy}=await import('../public/sync-protocol.mjs');
 const tasks=[{id:'t',title:'Old',sessions:[]}];
 const one=importLegacy(tasks,'legacy-a');const deleted=changeEntity(one,'a',['task','t'],{$alive:false});
 const two=importLegacy([{...tasks[0],title:'unsent edit'}],'legacy-b');
 const p=projectDocument(mergeDocuments(deleted,two));
 assert.equal(p.entities[0].deleted,true);assert.deepEqual(p.conflicts.map(c=>c.field),['$alive','title']);
});
test('reject collisions, gaps, unsafe JSON, future schema and preserve extensions',async()=>{
 const {validateDocument}=await import('../public/sync-protocol.mjs');
 const a=changeEntity(emptyDocument(),'a',['task','t'],{title:'x',custom:{a:[1,null]}});
 assert.throws(()=>mergeDocuments(a,changeEntity(emptyDocument(),'a',['task','t'],{title:'y'})),/Коллизия/);
 const gap=structuredClone(a);gap.ops[0].seq=2;gap.ops[0].seen={a:1};assert.throws(()=>validateDocument(gap),/Неполный/);
 const missing=structuredClone(a);missing.ops[0].seen={b:1};assert.throws(()=>validateDocument(missing),/предшественник/);
 assert.throws(()=>validateDocument({...a,version:3}),/Неподдерживаемый/);
 assert.throws(()=>changeEntity(a,'b',['task','t'],{bad:NaN}),/JSON/);
 assert.throws(()=>changeEntity(a,'__proto__',['task','t'],{title:'bad'}));
 const extension={...a,extension:{future:'preserved'}};assert.deepEqual(mergeDocuments(extension,a).extension,{future:'preserved'});
 assert.throws(()=>mergeDocuments(extension,{...a,extension:'other'}),/расширения/);
});
test('imports and projects a 100-session history without dropping metadata',async()=>{
 const {importLegacy,projectTasks}=await import('../public/sync-protocol.mjs');
 const tasks=[{id:'t',title:'History',sessions:Array.from({length:100},(_,i)=>({id:String(i).padStart(3,'0'),started_at:'2026-01-01T10:00:00Z',ended_at:'2026-01-01T11:00:00Z',comment:`session ${i}`,custom:{n:i}}))}];
 const start=performance.now();const doc=importLegacy(tasks,'legacy');assert.deepEqual(projectTasks(doc).tasks,tasks);
 console.log(`100-session import/projection: ${Math.round(performance.now()-start)}ms`);
});
test('interval cannot overwrite IDs or object prototypes',()=>{
 assert.throws(()=>changeEntity(emptyDocument(),'a',['session','t','s'],{interval:JSON.parse('{"id":"different","__proto__":{"polluted":true}}')}),/интервал/);
});
test('numeric JSON lexical differences coalesce and invalid Unicode is rejected',async()=>{
 const {validateDocument}=await import('../public/sync-protocol.mjs');
 const a=changeEntity(emptyDocument(),'a',['task','t'],{title:'x',number:1});
 const b=JSON.parse(JSON.stringify(changeEntity(emptyDocument(),'b',['task','t'],{title:'x',number:1})).replace('"number":1','"number":1.0'));
 assert.equal(projectDocument(mergeDocuments(a,b)).conflicts.length,0);
 assert.throws(()=>validateDocument({...a,extension:'\ud800'}),/Unicode/);
});
