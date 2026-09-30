import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState, apply, validateBackup, sessionSeconds, totalSeconds} from '../public/model.mjs';
const t0='2026-09-30T10:00:00.000Z', t1='2026-09-30T10:01:00.000Z', t2='2026-09-30T10:02:00.000Z';
const create=(s=initialState(),title='Задача')=>apply(s,{type:'createTask',values:{title,day:'2026-09-30'}},t0);
test('switch, repeated start, pause and complete preserve one active session and immutable input',()=>{
 const original=initialState(); let s=create(original); s=create(s,'Вторая'); const [a,b]=s.tasks.map(t=>t.id);
 assert.throws(()=>apply(s,{type:'updateTask',taskId:a,values:{priority:5}},t0));
 assert.throws(()=>apply(s,{type:'updateTask',taskId:'missing',values:{title:'x'}},t0));
 assert.throws(()=>apply(s,{type:'createTask',values:{title:'   '}},t0));
 assert.deepEqual(original,initialState()); assert.equal(s.tasks[0].priority,4);
 const before=structuredClone(s); s=apply(s,{type:'startTask',taskId:a},t0); assert.deepEqual(before.tasks[0].sessions,[]);
 s=apply(s,{type:'startTask',taskId:a},t1); assert.equal(s.tasks[0].sessions.length,1);
 s=apply(s,{type:'startTask',taskId:b},t1); assert.equal(s.tasks[0].status,'paused'); assert.equal(totalSeconds(s.tasks[0],t2),60);
 s=apply(s,{type:'pauseTask',taskId:b},t2); assert.equal(totalSeconds(s.tasks[1],t2),60);
 s=apply(s,{type:'completeTask',taskId:b},t2); assert.equal(s.tasks[1].status,'completed');
});
test('session edits retain metadata and timestamp bytes; reject invalid dates and reopening',()=>{
 let s=create();const taskId=s.tasks[0].id;
 s=apply(s,{type:'addSession',taskId,values:{started_at:'2026-09-29T23:59:00.123456+03:00',ended_at:'2026-09-30T00:01:00.123456+03:00',comment:'x'}},t0);
 const sessionId=s.tasks[0].sessions[0].id;s.tasks[0].sessions[0].bitrix_record_id='123';
 s=apply(s,{type:'completeTask',taskId},t0);
 s=apply(s,{type:'updateSession',taskId,sessionId,values:{comment:'y'}},t1);
 assert.equal(s.tasks[0].sessions[0].started_at,'2026-09-29T23:59:00.123456+03:00');assert.equal(s.tasks[0].sessions[0].bitrix_record_id,'123');assert.equal(s.tasks[0].status,'completed');assert.equal(totalSeconds(s.tasks[0]),120);
 assert.throws(()=>apply(s,{type:'updateSession',taskId,sessionId,values:{ended_at:null}},t1));
 assert.throws(()=>apply(s,{type:'addSession',taskId,values:{started_at:'2026-02-30T10:00',ended_at:t1}},t1));
 assert.throws(()=>apply(s,{type:'addSession',taskId,values:{started_at:t1,ended_at:t0}},t1));
 s=apply(s,{type:'deleteSession',taskId,sessionId},t1);assert.equal(s.tasks[0].sessions.length,0);assert.equal(s.tasks[0].status,'completed');
});
test('focus expires at stored deadline after sleep and active changes cancel it',()=>{
 let s=create();const taskId=s.tasks[0].id;
 s=apply(s,{type:'startFocus',taskId,values:{minutes:1}},t0);
 assert.throws(()=>apply(s,{type:'startFocus',taskId,values:{minutes:2}},t0));
 const asleep=apply(s,{type:'reconcile'},t2);assert.equal(asleep.tasks[0].sessions[0].ended_at,t1);assert.equal(asleep.focus,null);assert.equal(totalSeconds(asleep.tasks[0]),60);
 const stopped=apply(s,{type:'stopFocus'},'2026-09-30T10:00:30.000Z');assert.equal(stopped.tasks[0].status,'paused');assert.equal(totalSeconds(stopped.tasks[0]),30);
 const removed=apply(s,{type:'deleteSession',taskId,sessionId:s.tasks[0].sessions[0].id},t0);assert.equal(removed.focus,null);
 for(const minutes of [0,181,1.5])assert.throws(()=>apply(s,{type:'startFocus',taskId,values:{minutes}},t2));
 const deleted=apply(s,{type:'deleteTask',taskId},t0);assert.equal(deleted.tasks.length,0);assert.equal(deleted.focus,null);
 const completed=apply(s,{type:'completeTask',taskId},t0);assert.equal(completed.focus,null);assert.equal(completed.tasks[0].status,'completed');
});
test('backup validates full state, preserves unknown metadata and rejects corrupt or ambiguous snapshots',()=>{
 let s=create();s.custom={future:true};s.tasks[0].bitrix={id:'9'};
 const restored=validateBackup(s);assert.deepEqual(restored,s);restored.tasks[0].title='Другой';assert.equal(s.tasks[0].title,'Задача');
 for(const bad of [null,[],{...s,schemaVersion:2},{...s,tasks:[s.tasks[0],s.tasks[0]]},{...s,focus:{taskId:'missing',started_at:t0,ends_at:t1}}])assert.throws(()=>validateBackup(bad));
 const invalid=structuredClone(s);invalid.tasks[0].day='2026-02-29';assert.throws(()=>validateBackup(invalid));
 const running=apply(s,{type:'startTask',taskId:s.tasks[0].id},t0);assert.deepEqual(validateBackup(running),running);
 const bad=structuredClone(running);bad.tasks[0].status='completed';assert.throws(()=>validateBackup(bad));
 assert.deepEqual(apply(s,{type:'replaceState',values:running},t0),running);
});
test('comment-only edit remains possible for immediately stopped timer',()=>{
 let s=create();const taskId=s.tasks[0].id;s=apply(s,{type:'startTask',taskId},t0);s=apply(s,{type:'pauseTask',taskId},t0);
 const sessionId=s.tasks[0].sessions[0].id;
 s=apply(s,{type:'updateSession',taskId,sessionId,values:{comment:'Случайный запуск',started_at:t0,ended_at:t0}},t1);
 assert.equal(s.tasks[0].sessions[0].comment,'Случайный запуск');assert.deepEqual(validateBackup(s),s);
});
test('editing focused session cannot persist a start later than the focus start',()=>{
 let s=create();const taskId=s.tasks[0].id;
 s=apply(s,{type:'startFocus',taskId,values:{minutes:25}},t0);
 const sessionId=s.tasks[0].sessions[0].id;
 assert.throws(()=>apply(s,{type:'updateSession',taskId,sessionId,values:{started_at:t2}},'2026-09-30T10:05:00.000Z'),/концентрации/);
 const edited=apply(s,{type:'updateSession',taskId,sessionId,values:{started_at:'2026-09-30T09:59:00.000Z',comment:'Уточнение'}},'2026-09-30T10:05:00.000Z');
 assert.deepEqual(validateBackup(edited),edited);
 assert.deepEqual(validateBackup(s),s);
});
test('clock rollback cannot create focus preceding existing active session',()=>{
 let s=create();const taskId=s.tasks[0].id;
 s=apply(s,{type:'startTask',taskId},t2);assert.deepEqual(validateBackup(s),s);
 assert.throws(()=>apply(s,{type:'startFocus',taskId,values:{minutes:25}},t0),/начала сессии/);
 const focused=apply(s,{type:'startFocus',taskId,values:{minutes:25}},t2);
 assert.deepEqual(validateBackup(focused),focused);
});
