import test from 'node:test';
import assert from 'node:assert/strict';
import {synchronize} from '../public/sync-controller.mjs';
import {emptyDocument} from '../public/sync-protocol.mjs';

test('first v2 creation reads legacy without overwriting it and preserves unknown metadata',async()=>{
 const legacy={tasks:[],extension:{preserve:'value'}};const log=[];
 const repo={enableSync:async()=>{},needsLegacyImport:async()=>true,markRemoteSeen:async()=>{},importRemoteLegacy:async value=>log.push(value),mergeSync:async()=>({document:emptyDocument(),state:{tasks:[]}})};
 const client={read:async()=>null,write:async(_,condition)=>log.push(condition)};
 await synchronize(repo,client,{legacyClient:{readLegacy:async()=>({body:JSON.stringify(legacy),etag:'"old"'})}});
 assert.deepEqual(log[0],legacy);assert.equal(log[1].create,true);assert.equal(log[1].etag,undefined);
});
test('existing v2 never reimports legacy and bounded conflicts reread before retry',async()=>{
 let reads=0,writes=0;const doc=emptyDocument();const repo={enableSync:async()=>{},needsLegacyImport:async()=>true,markRemoteSeen:async()=>{},mergeSync:async()=>({document:doc,state:{tasks:[]}})};
 await assert.rejects(synchronize(repo,{read:async()=>{reads++;return {body:JSON.stringify(doc),etag:'"v"'};},write:async()=>{writes++;throw Object.assign(new Error('precondition'),{code:412});}},{legacyClient:{readLegacy:()=>{throw Error('must not import');}}}),/precondition/);
 assert.equal(reads,3);assert.equal(writes,3);
});
test('future schema and network error never trigger unsafe write or retries',async()=>{
 let writes=0;const repo={enableSync:async()=>{},needsLegacyImport:async()=>true,markRemoteSeen:async()=>{},mergeSync:async()=>{throw Error('must not merge');}};
 await assert.rejects(synchronize(repo,{read:async()=>({body:'{"format":"tasktimer-sync","version":3,"ops":[]}',etag:'"v"'}),write:()=>writes++}),/Неподдерживаемый/);assert.equal(writes,0);
 let reads=0;await assert.rejects(synchronize(repo,{read:async()=>{reads++;throw Error('network');}}),/network/);assert.equal(reads,1);
});

test('legacy migration rejects future schema and embedded causal format before import',async()=>{
 for(const snapshot of [{tasks:[],schemaVersion:9},{tasks:[],sync_v2:{version:2}},{tasks:[],_sync_v2:{version:2}},{tasks:[],syncDocument:{version:2}}]){
  let imported=false,written=false;const repo={enableSync:async()=>{},needsLegacyImport:async()=>true,importRemoteLegacy:async()=>{imported=true;}};
  await assert.rejects(synchronize(repo,{read:async()=>null,write:async()=>{written=true;}},{legacyClient:{readLegacy:async()=>({body:JSON.stringify(snapshot)})}}),/Неподдерживаемый/);
  assert.equal(imported,false);assert.equal(written,false);
 }
});
