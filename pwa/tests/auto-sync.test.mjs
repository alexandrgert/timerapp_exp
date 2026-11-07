import test from 'node:test';
import assert from 'node:assert/strict';
import {createAutoSync} from '../public/auto-sync.mjs';
function fixture({run,eligible}={}){
 let time=0,id=0;const timers=new Map(),calls=[],statuses=[];let revision='a';
 const scheduler=createAutoSync({now:()=>time,setTimer:(fn,ms)=>{timers.set(++id,{fn,at:time+ms});return id;},clearTimer:id=>timers.delete(id),eligible,onStatus:s=>statuses.push(s),run:async()=>{calls.push(time);return run?await run():{revision};}});
 async function advance(ms){const end=time+ms;while(true){const next=[...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;time=next[1].at;timers.delete(next[0]);next[1].fn();await new Promise(resolve=>setImmediate(resolve));}time=end;await new Promise(resolve=>setImmediate(resolve));}
 return {scheduler,calls,statuses,advance,revision:value=>{revision=value;scheduler.observe(value);}};
}
test('auto sync is opt-in, debounces local changes and polls without second ticks causing writes',async()=>{
 const f=fixture();f.revision('a');await f.advance(200000);assert.equal(f.calls.length,0);f.scheduler.setEnabled(true);await f.advance(0);assert.equal(f.calls.length,1);
 f.revision('b');await f.advance(5000);f.revision('c');await f.advance(9999);assert.equal(f.calls.length,1);await f.advance(1);assert.equal(f.calls.length,2);await f.advance(119999);assert.equal(f.calls.length,2);await f.advance(1);assert.equal(f.calls.length,3);f.scheduler.dispose();await f.advance(500000);assert.equal(f.calls.length,3);
});
test('local changes during upload get a trailing exchange but matching remote merge does not loop',async()=>{
 let release;const f=fixture({run:()=>new Promise(resolve=>release=resolve)});f.revision('a');f.scheduler.setEnabled(true);await f.advance(0);f.revision('b');release({revision:'a'});await f.advance(0);await f.advance(9999);assert.equal(f.calls.length,1);await f.advance(1);assert.equal(f.calls.length,2);release({revision:'b'});await f.advance(0);await f.advance(10000);assert.equal(f.calls.length,2);f.scheduler.dispose();
});
test('hidden/offline/conflict eligibility waits for an explicit wake trigger',async()=>{
 let reason='Офлайн';const f=fixture({eligible:()=>reason});f.revision('a');f.scheduler.setEnabled(true);await f.advance(0);assert.equal(f.calls.length,0);await f.advance(300000);assert.equal(f.calls.length,0);reason=null;f.scheduler.trigger();await f.advance(0);assert.equal(f.calls.length,1);f.scheduler.dispose();
});
test('network failures back off, rate-limit retryAt wins, and permanent auth waits for reset',async()=>{
 let error=Object.assign(new Error('network'),{code:'NETWORK'});const f=fixture({run:()=>{if(error)throw error;return {revision:'a'};}});f.revision('a');f.scheduler.setEnabled(true);await f.advance(0);assert.equal(f.calls.length,1);f.scheduler.trigger();await f.advance(29999);assert.equal(f.calls.length,1);await f.advance(1);assert.equal(f.calls.length,2);
 error=Object.assign(new Error('limited'),{code:'RATE_LIMIT',retryAt:400000});await f.advance(60000);assert.equal(f.calls.length,3);f.scheduler.trigger();await f.advance(309999);assert.equal(f.calls.length,3);await f.advance(1);assert.equal(f.calls.length,4);
 error=Object.assign(new Error('auth'),{code:'AUTH'});f.scheduler.reset();await f.advance(10000);assert.equal(f.calls.length,5);await f.advance(1000000);f.scheduler.trigger();await f.advance(1000000);assert.equal(f.calls.length,5);error=null;f.scheduler.reset();await f.advance(10000);assert.equal(f.calls.length,6);f.scheduler.dispose();
});
test('manual acknowledgement clears a paused error and schedules normal polling',async()=>{
 const f=fixture();f.revision('a');f.scheduler.setEnabled(true);await f.advance(0);f.scheduler.failed(Object.assign(new Error('invalid token'),{code:'AUTH'}));f.scheduler.acknowledge('a');await f.advance(119999);assert.equal(f.calls.length,1);await f.advance(1);assert.equal(f.calls.length,2);f.scheduler.setEnabled(false);await f.advance(500000);assert.equal(f.calls.length,2);
});
