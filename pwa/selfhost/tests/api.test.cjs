const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),{openStore}=require('../store.cjs'),{running,origin}=require('./helpers.cjs');
const protocol=()=>import('../../public/sync-protocol.mjs');
test('API authenticates, validates origin, enforces CAS and retains acknowledged history',async t=>{
 const s=await running(t),{emptyDocument,changeEntity}=await protocol();
 assert.equal((await s.request('/api/sync')).status,401);
 assert.equal((await s.request('/api/sync',{headers:{...s.auth,Origin:'https://elsewhere.test'}})).status,403);
 assert.equal((await s.request('/api/sync',{headers:s.auth})).status,404);
 const doc=changeEntity(emptyDocument(),'device-a',['task','t'],{title:'Задача'}),headers={...s.auth,'Content-Type':'application/json','If-None-Match':'*'};
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:{...s.auth,'Content-Type':'application/json'},body:JSON.stringify(doc)})).status,428);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:{...headers,'If-None-Match':'invalid'},body:JSON.stringify(doc)})).status,428);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers,body:'{}'})).status,400);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers,body:JSON.stringify(doc)})).status,204);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers,body:JSON.stringify(doc)})).status,412);
 const prior=await s.request('/api/sync',{headers:{...s.auth,Origin:origin}});assert.equal(prior.status,200);assert.equal(prior.headers['cache-control'],'no-store');assert.equal(JSON.parse(prior.body).ops.length,1);
 const condition={...s.auth,'Content-Type':'application/json','If-Match':prior.headers.etag};
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:condition,body:JSON.stringify(emptyDocument())})).status,409);
 const updated=changeEntity(doc,'device-b',['task','t'],{description:'Правка'});
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:condition,body:JSON.stringify(updated)})).status,204);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:condition,body:JSON.stringify(updated)})).status,412);
 assert.equal((await s.request('/api/sync',{method:'PUT',headers:{...condition,'Content-Length':String(21*1024*1024)}})).status,413);
 const store=openStore(s.data);store.revoke(s.device.id);store.close();assert.equal((await s.request('/api/sync',{headers:s.auth})).status,401);
});
test('SQLite backup/reopen preserves state and device revocation, future schema fails closed',async t=>{
 const s=await running(t),{emptyDocument}=await protocol(),a=openStore(s.data),b=openStore(s.data),body=JSON.stringify(emptyDocument());
 const etag=a.write(body,{create:true});assert.ok(etag);assert.equal(b.write(body,{create:true}),false);
 const copy=path.join(s.data,'backup.sqlite');await a.backup(copy);await assert.rejects(a.backup(copy));a.close();b.close();
 const db=new (require('node:sqlite').DatabaseSync)(copy);assert.equal(db.prepare('SELECT body FROM state').get().body,body);assert.equal(db.prepare('SELECT revoked FROM devices').get().revoked,0);db.close();
 const text=(await fs.readFile(copy)).toString();assert.equal(text.includes(s.device.token),false);assert.equal((await fs.stat(copy)).mode&0o777,0o600);
 const reopened=openStore(s.data);assert.equal(reopened.read().body,body);assert.equal(reopened.authorized(s.device.token),true);reopened.close();
 const separate=path.join(s.data,'future');await fs.mkdir(separate);const future=new (require('node:sqlite').DatabaseSync)(path.join(separate,'tasktimer.sqlite'));future.exec('PRAGMA user_version=999');future.close();assert.throws(()=>openStore(separate),/Unsupported database version/);
});
test('self-host frontend serves own transport and guide without changing normal GitHub sources',async t=>{
 const s=await running(t),html=(await s.request('/')).body.toString(),app=(await s.request('/app.mjs')).body.toString(),client=(await s.request('/github-client.mjs')).body.toString();
 assert.ok(html.includes('Синхронизация со своим сервером'));assert.ok(html.includes('name="repository" type="hidden"'));assert.ok(html.includes('href="/server-guide/"'));assert.ok(!html.includes('Fine-grained'));
 assert.ok(client.includes("'/api/sync'"));assert.ok(!client.includes('api.github.com'));assert.ok(app.includes('createGitHubClient'));
 assert.equal((await s.request('/server-guide/')).status,200);assert.ok((await s.request('/guide/')).headers['content-security-policy'].includes("img-src 'self' data:"));assert.equal((await s.request('/api/tasktimer.sqlite',{headers:s.auth})).status,404);assert.equal((await s.request('/selfhost/store.cjs')).status,404);
 const sw=(await s.request('/sw.js')).body.toString();assert.ok(!sw.includes('__TASKTIMER_REVISION__'));assert.ok(!sw.includes("'/api/sync'"));
});
test('concurrent independent server processes cannot overwrite the same revision',async t=>{
 const s=await running(t),store=openStore(s.data),body='{"format":"tasktimer-sync","version":2,"ops":[]}',etag=store.write(body,{create:true});store.close();
 const {spawn}=require('node:child_process'),script=`const {openStore}=require(process.argv[1]);const s=openStore(process.argv[2]);try{console.log(!!s.write(process.argv[4],{etag:process.argv[3],create:false}));}finally{s.close();}`;
 const run=value=>new Promise((resolve,reject)=>{const c=spawn(process.execPath,['-e',script,path.resolve(__dirname,'../store.cjs'),s.data,etag,value],{stdio:['ignore','pipe','pipe']});let result='';c.stdout.on('data',b=>result+=b);c.on('error',reject);c.on('exit',code=>code===0?resolve(result.trim()):reject(Error('CAS child failed')));});
 const result=await Promise.all([run('{"a":1}'),run('{"b":2}')]);assert.deepEqual(result.sort(),['false','true']);
});
test('storage failure returns 503 without discarding acknowledged document',async t=>{
 const s=await running(t),{emptyDocument,changeEntity}=await protocol();const store=openStore(s.data),doc=emptyDocument(),etag=store.write(JSON.stringify(doc),{create:true});store.close();
 const db=new (require('node:sqlite').DatabaseSync)(path.join(s.data,'tasktimer.sqlite'));db.exec("CREATE TRIGGER simulate_full BEFORE UPDATE ON state BEGIN SELECT RAISE(FAIL,'database or disk is full'); END");db.close();
 const updated=changeEntity(doc,'a',['task','t'],{title:'Keep locally'}),r=await s.request('/api/sync',{method:'PUT',headers:{...s.auth,'Content-Type':'application/json','If-Match':etag},body:JSON.stringify(updated)});assert.equal(r.status,503);assert.deepEqual(JSON.parse((await s.request('/api/sync',{headers:s.auth})).body),doc);
});
test('admin migration imports v2 causality only into an empty database',async t=>{
 const s=await running(t),{emptyDocument,changeEntity}=await protocol(),{execFile}=require('node:child_process'),{promisify}=require('node:util');const run=promisify(execFile),file=path.join(s.data,'export.json'),doc=changeEntity(emptyDocument(),'original-device',['task','original-task'],{title:'Import'});await fs.writeFile(file,JSON.stringify(doc));
 const args=[path.resolve(__dirname,'../admin.cjs'),'import-v2',file],options={env:{...process.env,CLOUDCLI_DATA_DIR:s.data}};await run(process.execPath,args,options);assert.deepEqual(JSON.parse((await s.request('/api/sync',{headers:s.auth})).body),doc);await assert.rejects(run(process.execPath,args,options));assert.deepEqual(JSON.parse((await s.request('/api/sync',{headers:s.auth})).body),doc);
});
test('missing tables in an existing schema never recreate an empty dataset',async t=>{
 const s=await running(t),damaged=path.join(s.data,'damaged');await fs.mkdir(damaged);const filename=path.join(damaged,'tasktimer.sqlite'),db=new (require('node:sqlite').DatabaseSync)(filename);db.exec('PRAGMA user_version=1; CREATE TABLE evidence(value TEXT); INSERT INTO evidence VALUES(\'preserve\');');db.close();assert.throws(()=>openStore(damaged));const check=new (require('node:sqlite').DatabaseSync)(filename);assert.equal(check.prepare('SELECT value FROM evidence').get().value,'preserve');assert.equal(check.prepare("SELECT name FROM sqlite_master WHERE name='state'").get(),undefined);check.close();
});

test('server API roundtrips a UTF-8 sync document larger than one megabyte without changing its version',async t=>{
 const s=await running(t),{importLegacy}=await protocol(),{apply,initialState}=await import('../../public/model.mjs');let state=initialState();
 for(let i=0;i<40;i++)state=apply(state,{type:'createTask',values:{title:'Большой документ '+i,description:'я'.repeat(15000)}});
 const body=JSON.stringify(importLegacy(state.tasks,'large-seed'));assert.ok(Buffer.byteLength(body)>1_000_000);
 const put=await s.request('/api/sync',{method:'PUT',headers:{...s.auth,'Content-Type':'application/json','If-None-Match':'*'},body});assert.equal(put.status,204);
 const get=await s.request('/api/sync',{headers:s.auth});assert.equal(get.status,200);assert.equal(get.body.toString(),body);assert.equal(get.headers.etag,put.headers.etag);
});
