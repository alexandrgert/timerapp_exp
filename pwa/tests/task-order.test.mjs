import test from 'node:test';
import assert from 'node:assert/strict';
import {apply,initialState,validateBackup} from '../public/model.mjs';
import {visibleTasks} from '../public/desktop-domain.mjs';
const now='2026-10-07T10:00:00',day='2026-10-07';
function fixture(){let s=initialState();for(const [title,priority] of [['A',1],['B',2],['C',4],['D',3]])s=apply(s,{type:'createTask',values:{title,priority,day}},now);return s;}
const names=(s,options={})=>visibleTasks(s,{view:'today',day,...options},now).map(t=>t.title);
const move=(s,from,to,position='before')=>apply(s,{type:'reorderTask',taskId:s.tasks.find(t=>t.title===from).id,values:{targetId:s.tasks.find(t=>t.title===to).id,position,day,view:'today'}},now);
test('free ordering crosses priorities, persists in backup, and leaves task data untouched',()=>{
 const before=fixture(),s=move(before,'C','A');assert.deepEqual(names(s),['C','A','B','D']);assert.deepEqual(s.tasks,before.tasks);
 assert.deepEqual(names(validateBackup(JSON.parse(JSON.stringify(s))),{view:'all'}),['C','A','B','D']);
 assert.deepEqual(names(s,{priorities:[1,4]}),['C','A']);
 assert.deepEqual(names(move(s,'A','D','after')),['C','B','D','A']);
});
test('active task pins above manual order and returns after pause; stale active or deleted moves fail',()=>{
 let s=move(fixture(),'C','A');const b=s.tasks.find(t=>t.title==='B').id;
 s=apply(s,{type:'startTask',taskId:b},now);assert.deepEqual(names(s),['B','C','A','D']);assert.throws(()=>move(s,'B','A'));assert.throws(()=>move(s,'C','B'));
 s=apply(s,{type:'pauseTask',taskId:b},now);assert.deepEqual(names(s),['C','A','B','D']);
 s=apply(s,{type:'deleteTask',taskId:b},now);assert.ok(!s.taskOrder.includes(b));assert.throws(()=>apply(s,{type:'reorderTask',taskId:b,values:{targetId:s.tasks[0].id,position:'before'}},now));
});
test('successive relative moves preserve other ordering and append new tasks deterministically',()=>{
 let s=move(fixture(),'C','A');s=move(s,'D','A');s=move(s,'B','C');assert.deepEqual(names(s),['B','C','D','A']);
 s=apply(s,{type:'createTask',values:{title:'E',day}},now);assert.deepEqual(names(s),['B','C','D','A','E']);
 assert.throws(()=>validateBackup({...s,taskOrder:[s.tasks[0].id,s.tasks[0].id]}));
});
