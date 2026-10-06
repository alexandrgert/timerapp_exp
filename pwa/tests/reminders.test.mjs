import test from 'node:test';
import assert from 'node:assert/strict';
import {apply,initialState} from '../public/model.mjs';
const at=m=>new Date(Date.UTC(2026,9,6,9,m)).toISOString();
function running(){let s=apply(initialState(),{type:'createAndStartTask',values:{title:'Работа',day:'2026-10-06'}},at(0));return s;}
test('overdue unseen reminder never stops timer; only shown prompt arms five-minute deadline',()=>{
 let s=running();s=apply(s,{type:'reconcile'},at(80));assert.equal(s.tasks[0].status,'running');assert.ok(s.reminder.pending);assert.equal(s.reminder.pending.deadline,null);
 const expected=structuredClone(s.reminder.pending);
 s=apply(s,{type:'reminder',values:{action:'shown',expected}},at(80));assert.equal(s.reminder.pending.deadline,at(85));
 s=apply(s,{type:'reconcile'},at(84));assert.equal(s.tasks[0].status,'running');
 s=apply(s,{type:'reconcile'},at(90));assert.equal(s.tasks[0].status,'paused');assert.equal(s.tasks[0].sessions[0].ended_at,at(85));
});
test('restoring a backup starts a fresh interval and never imports an armed stop',()=>{
 let s=running();s=apply(s,{type:'reminder',values:{action:'shown',expected:s.reminder.pending}},at(40));
 const restored=apply(initialState(),{type:'replaceState',values:s},at(50));assert.equal(restored.tasks[0].status,'running');assert.equal(restored.reminder.pending.deadline,null);assert.equal(restored.reminder.pending.dueAt,at(90));
});
test('stale answers and edited/replaced sessions cannot stop a different interval',()=>{
 let s=running();const old=structuredClone(s.reminder.pending);
 s=apply(s,{type:'reminder',values:{action:'shown',expected:old}},at(40));const shown=structuredClone(s.reminder.pending);
 s=apply(s,{type:'reminder',values:{action:'continue',expected:shown}},at(41));assert.equal(s.reminder.pending.dueAt,at(81));
 s=apply(s,{type:'reminder',values:{action:'stop',expected:shown}},at(42));assert.equal(s.tasks[0].status,'running');
 s=apply(s,{type:'updateSession',taskId:s.tasks[0].id,sessionId:old.sessionId,values:{started_at:at(20),ended_at:null}},at(42));
 assert.notEqual(s.reminder.pending.generation,shown.generation);assert.equal(s.reminder.pending.deadline,null);
 s=apply(s,{type:'reminder',values:{action:'stop',expected:shown}},at(43));assert.equal(s.tasks[0].status,'running');
});
test('disable, concentration, midnight and invalid settings cancel unsafe reminders',()=>{
 let s=running();s=apply(s,{type:'reminder',values:{action:'shown',expected:s.reminder.pending}},at(40));
 s=apply(s,{type:'reminder',values:{action:'settings',enabled:false,minutes:1}},at(41));s=apply(s,{type:'reconcile'},at(90));assert.equal(s.tasks[0].status,'running');assert.equal(s.reminder.pending,null);
 for(const minutes of [0,1441,1.5])assert.throws(()=>apply(s,{type:'reminder',values:{action:'settings',enabled:true,minutes}},at(91)));
 let f=running();f=apply(f,{type:'startFocus',values:{minutes:180}},at(40));assert.equal(f.reminder.pending,null);f=apply(f,{type:'reconcile'},at(90));assert.equal(f.tasks.at(-1).status,'running');assert.equal(f.reminder.pending,null);
 let midnight=running();midnight=apply(midnight,{type:'reconcile'},'2026-10-07T12:00:00Z');assert.equal(midnight.tasks[0].status,'paused');assert.equal(midnight.reminder.pending,null);
});
test('stop pauses without completing and reload preserves an already shown deadline',()=>{
 let s=running();s=apply(s,{type:'reminder',values:{action:'shown',expected:s.reminder.pending}},at(40));const p=structuredClone(s.reminder.pending);
 s=apply(JSON.parse(JSON.stringify(s)),{type:'reconcile'},at(42));assert.equal(s.reminder.pending.deadline,at(45));
 s=apply(s,{type:'reminder',values:{action:'stop',expected:p}},at(43));assert.equal(s.tasks[0].status,'paused');assert.equal(s.tasks[0].completed_at,null);assert.equal(s.tasks[0].sessions[0].ended_at,at(43));
});
test('overdue shown reminder closes at the earlier of response deadline and local day boundary',()=>{
 for(const hour of [22,23]){
  const start=new Date(2026,9,6,hour,58,0).toISOString();
  let s=apply(initialState(),{type:'createAndStartTask',values:{title:'Поздно',day:'2026-10-06'}},start);
  s=apply(s,{type:'reminder',values:{action:'settings',enabled:true,minutes:1}},start);
  const shown=new Date(2026,9,6,hour,59,0).toISOString();
  s=apply(s,{type:'reminder',values:{action:'shown',expected:s.reminder.pending}},shown);
  s=apply(s,{type:'reconcile'},new Date(2026,9,7,8).toISOString());
  const expected=hour===22?new Date(2026,9,6,23,4,0).toISOString():new Date(2026,9,6,23,59,59).toISOString();
  assert.equal(s.tasks[0].sessions[0].ended_at,expected);assert.equal(s.reminder.pending,null);
 }
});
