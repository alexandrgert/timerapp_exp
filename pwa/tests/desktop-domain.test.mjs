import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState,apply,totalSeconds,validateBackup} from '../public/model.mjs';
const at='2026-10-05T10:00:00.000Z';
test('desktop focus pauses task, records separate session and requires explicit resume',()=>{
 let s=apply(initialState(),{type:'createTask',values:{title:'Работа'}},at); const previous=s.tasks[0].id;
 s=apply(s,{type:'startTask',taskId:previous},at);
 s=apply(s,{type:'startFocus',values:{minutes:1}},'2026-10-05T10:01:00.000Z');
 assert.equal(s.tasks.length,2);assert.equal(s.tasks[0].status,'paused');assert.equal(totalSeconds(s.tasks[0]),60);
 const focusId=s.focus.taskId;s=apply(s,{type:'reconcile'},'2026-10-05T10:03:00.000Z');
 assert.equal(s.tasks.find(t=>t.id===focusId).status,'completed');assert.equal(totalSeconds(s.tasks[1]),60);assert.equal(s.focusResumeTaskId,previous);
 s=apply(s,{type:'resumeFocusTask'},'2026-10-05T10:04:00.000Z');assert.equal(s.tasks[0].status,'running');assert.equal(s.tasks[0].sessions.length,2);assert.equal(s.focusResumeTaskId,null);validateBackup(s);
});
test('day boundary closes prior session, carries only yesterday plan and preserves explicit priority four',()=>{
 let s=apply(initialState(),{type:'createTask',values:{title:'Работа',keep_priority:true,priority:4}},'2026-10-04T23:58:00');
 const id=s.tasks[0].id;s=apply(s,{type:'startTask',taskId:id},'2026-10-04T23:58:00');
 s=apply(s,{type:'reconcile'},'2026-10-05T09:00:00');
 assert.equal(totalSeconds(s.tasks[0]),119);assert.equal(s.tasks[0].status,'paused');
 assert.ok(s.tasks[0].planned_days.includes('2026-10-05'));assert.equal(s.tasks[0].daily_priorities['2026-10-05'],4);
 s=apply(s,{type:'removeFromPlan',taskId:id,values:{day:'2026-10-05'}},'2026-10-05T10:00:00');assert.equal(s.tasks[0].daily_priorities['2026-10-05'],undefined);
 s=apply(s,{type:'assignPriority',taskIds:[id],values:{day:'2026-10-05',priority:2}},'2026-10-05T10:00:00');assert.ok(s.tasks[0].planned_days.includes('2026-10-05'));assert.equal(s.tasks[0].daily_priorities['2026-10-05'],2);
 const later=apply(s,{type:'reconcile'},'2026-10-07T09:00:00');assert.ok(!later.tasks[0].planned_days.includes('2026-10-07'));
});
test('desktop day queries allocate whole interval to local start day and report results',async()=>{
 const domain=await import('../public/desktop-domain.mjs');
 assert.equal(typeof domain.secondsOnDay,'function');
 let s=apply(initialState(),{type:'createTask',values:{title:'Ночная',result:'Готово'}},'2026-10-04T23:00:00');
 s=apply(s,{type:'addSession',taskId:s.tasks[0].id,values:{started_at:'2026-10-04T23:59:00',ended_at:'2026-10-05T00:01:00',comment:'Проверка'}},at);
 assert.equal(domain.secondsOnDay(s.tasks[0],'2026-10-04',at),120);assert.equal(domain.secondsOnDay(s.tasks[0],'2026-10-05',at),0);
 assert.equal(domain.visibleTasks(s,{view:'date',day:'2026-10-04'},at).length,1);
 const report=domain.buildDayReport(s,'2026-10-04',{extended:true,now:at});assert.match(report,/Итого:\*\* 00:02/);assert.match(report,/Готово/);assert.match(report,/Проверка/);
});
test('focus pause completes synthetic task; explicit switch clears offer and validation rejects malformed plan',()=>{
 let s=apply(initialState(),{type:'createTask',values:{title:'Работа'}},at),id=s.tasks[0].id;
 s=apply(s,{type:'startTask',taskId:id},at);s=apply(s,{type:'startFocus',values:{minutes:20}},at);
 const focusId=s.focus.taskId,paused=apply(s,{type:'pauseTask',taskId:focusId},'2026-10-05T10:01:00Z');
 assert.equal(paused.tasks[1].status,'completed');assert.equal(paused.focusResumeTaskId,id);
 const switched=apply(s,{type:'startTask',taskId:id},'2026-10-05T10:01:00Z');assert.equal(switched.focusResumeTaskId,null);assert.equal(switched.tasks[1].status,'completed');
 for(const patch of [{planned_days:'bad'},{daily_priorities:{'2026-10-05':5}},{keep_priority:1},{result:{}}]){
 const bad=structuredClone(s);Object.assign(bad.tasks[0],patch);assert.throws(()=>validateBackup(bad));
 }
});
test('local date accounting converts offsets, fractional midnight stays valid, resume cannot resurrect deleted tasks',async()=>{
 const {secondsOnDay,visibleTasks}=await import('../public/desktop-domain.mjs');
 const originalTZ=process.env.TZ;process.env.TZ='Europe/Moscow';
 try{
 let s=apply(initialState(),{type:'createTask',values:{title:'Полночь'}},'2026-10-05T21:30:00Z');assert.equal(s.tasks[0].day,'2026-10-06');
 const id=s.tasks[0].id;s=apply(s,{type:'addSession',taskId:id,values:{started_at:'2026-10-05T21:00:00Z',ended_at:'2026-10-05T22:00:00Z'}},'2026-10-05T23:00:00Z');
 assert.equal(secondsOnDay(s.tasks[0],'2026-10-06'),3600);assert.equal(secondsOnDay(s.tasks[0],'2026-10-05'),0);
 s=apply(s,{type:'startTask',taskId:id},'2026-10-06T23:59:59.500+03:00');s=apply(s,{type:'reconcile'},'2026-10-07T08:00:00+03:00');validateBackup(s);assert.equal(totalSeconds(s.tasks[0]),3600);
 s=apply(s,{type:'startFocus',values:{minutes:1}},'2026-10-07T08:00:00+03:00');s=apply(s,{type:'deleteTask',taskId:id},'2026-10-07T08:00:30+03:00');s=apply(s,{type:'reconcile'},'2026-10-07T08:02:00+03:00');assert.equal(s.focusResumeTaskId,null);assert.throws(()=>apply(s,{type:'resumeFocusTask'},'2026-10-07T08:02:00+03:00'));
 const focus=s.tasks[0];assert.equal(visibleTasks(s,{view:'today',day:'2026-10-07',priorities:[1]}).length,0);assert.ok(focus.planned_days.includes('2026-10-07'));
 }finally{if(originalTZ===undefined)delete process.env.TZ;else process.env.TZ=originalTZ;}
});
