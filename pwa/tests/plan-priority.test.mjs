import test from 'node:test';
import assert from 'node:assert/strict';
import {apply,initialState,validateBackup} from '../public/model.mjs';
import {priorityFor,visibleTasks} from '../public/desktop-domain.mjs';

test('removing a kept-priority plan moves it one calendar day without changing sessions or existing plans',()=>{
 const oldTZ=process.env.TZ;process.env.TZ='America/New_York';
 try{
 for(const [day,next] of [['2026-10-06','2026-10-07'],['2026-12-31','2027-01-01'],['2028-02-28','2028-02-29'],['2028-02-29','2028-03-01'],['2026-02-28','2026-03-01'],['2026-03-08','2026-03-09'],['2026-11-01','2026-11-02']]){
 for(const priority of [1,4]){
 const now=`${day}T12:00:00`;
 let state=apply(initialState(),{type:'createTask',values:{title:'Перенос',day,priority,keep_priority:true}},now);
 const id=state.tasks[0].id;
 state=apply(state,{type:'startTask',taskId:id},now);
 const sessions=structuredClone(state.tasks[0].sessions);
 const command={type:'removeFromPlan',taskId:id,values:{day}};
 const moved=apply(state,command,now);
 assert.deepEqual(moved.tasks[0].planned_days,[next],`${day} -> ${next}`);
 assert.equal(priorityFor(moved.tasks[0],day),priority);
 assert.equal(moved.tasks[0].priority,priority);
 assert.equal(moved.tasks[0].daily_priorities[next],priority);
 assert.deepEqual(moved.tasks[0].sessions,sessions);assert.equal(moved.tasks[0].status,'running');
 assert.deepEqual(apply(moved,command,now),moved,'duplicate removal is a no-op');
 const tomorrow=apply(moved,{type:'reconcile'},`${next}T12:00:00`);
 assert.equal(priorityFor(tomorrow.tasks[0],next),priority);
 assert.ok(visibleTasks(tomorrow,{view:'today',day:next},`${next}T12:00:00`).some(t=>t.id===id));
 assert.deepEqual(validateBackup(JSON.parse(JSON.stringify(moved))).tasks[0].daily_priorities,moved.tasks[0].daily_priorities);
 }
 }
 }finally{if(oldTZ===undefined)delete process.env.TZ;else process.env.TZ=oldTZ;}
});

test('plan removal respects disabled preservation, completed tasks, and explicit next-day priorities',()=>{
 const now='2026-10-06T12:00:00';
 for(const keep_priority of [false,true])for(const completed of [false,true])for(const nextPriority of [undefined,2,4]){
 let s=apply(initialState(),{type:'createTask',values:{title:'План',day:'2026-10-06',priority:1,keep_priority}},now);
 const id=s.tasks[0].id;
 s=apply(s,{type:'addToPlan',taskId:id,values:{day:'2026-10-04',priority:3}},now);
 if(nextPriority!==undefined)s=apply(s,{type:'addToPlan',taskId:id,values:{day:'2026-10-07',priority:nextPriority}},now);
 if(completed)s=apply(s,{type:'completeTask',taskId:id},now);
 s=apply(s,{type:'removeFromPlan',taskId:id,values:{day:'2026-10-06'}},now);
 assert.ok(!s.tasks[0].planned_days.includes('2026-10-06'));
 assert.equal(priorityFor(s.tasks[0],'2026-10-06'),keep_priority&&!completed?1:4);
 assert.equal(s.tasks[0].priority,keep_priority&&!completed?1:4);
 assert.equal(s.tasks[0].daily_priorities['2026-10-04'],3);
 assert.ok(s.tasks[0].planned_days.includes('2026-10-04'));
 assert.equal(s.tasks[0].daily_priorities['2026-10-07'],nextPriority??(keep_priority&&!completed?1:undefined));
 assert.equal(s.tasks[0].planned_days.includes('2026-10-07'),nextPriority!==undefined||keep_priority&&!completed);
 }
});

test('removing a selected future day uses its own date; repeated removal cannot restore a subsequently removed target',()=>{
 const now='2026-10-06T12:00:00';
 let s=apply(initialState(),{type:'createTask',values:{title:'Будущий план',day:'2026-12-31',priority:2,keep_priority:true}},now);
 const id=s.tasks[0].id,command={type:'removeFromPlan',taskId:id,values:{day:'2026-12-31'}};
 s=apply(s,command,now);
 assert.deepEqual(s.tasks[0].planned_days,['2027-01-01']);assert.equal(s.tasks[0].daily_priorities['2027-01-01'],2);
 s=apply(s,{type:'removeFromPlan',taskId:id,values:{day:'2027-01-01'}},now);
 const again=apply(s,command,now);assert.deepEqual(again,s);
 assert.deepEqual(again.tasks[0].planned_days,['2027-01-02']);
});
