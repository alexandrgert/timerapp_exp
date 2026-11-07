const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../public'),origin='https://github-sync.test';
async function setup(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--single-process','--no-zygote','--disable-dev-shm-usage']});
 const server={body:null,version:0,puts:0,private:true,status:null,failAfterPut:false,onPut:null};
 const context=await browser.newContext({serviceWorkers:'block'});let device=0;
 async function page(){const pageOrigin=origin.replace('.test','-'+(++device)+'.test');
 await context.route(pageOrigin+'/**',async route=>{const file=new URL(route.request().url()).pathname.slice(1)||'index.html';try{await route.fulfill({body:await fs.readFile(path.join(root,file)),contentType:file.endsWith('.html')?'text/html':file.endsWith('.css')?'text/css':'text/javascript'});}catch{await route.fulfill({status:404});}});
 await context.route('https://api.github.com/**',async route=>{const request=route.request(),url=new URL(request.url());assert.equal(request.headers().authorization,'Bearer example-test-token');const reply=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
 if(server.status)return reply({},server.status);
 if(url.pathname.endsWith('/private-data'))return reply({private:server.private});
 if(url.pathname.includes('/branches/'))return reply({name:'main'});
 assert.equal(url.pathname,'/repos/sample-owner/private-data/contents/data/state.v2.json');
 if(request.method()==='GET'){assert.equal(url.searchParams.get('ref'),'main');if(!server.body)return reply({},404);return reply({type:'file',path:'data/state.v2.json',sha:String(server.version).padStart(40,'0'),encoding:'base64',size:Buffer.byteLength(server.body),content:Buffer.from(server.body).toString('base64')});}
 assert.equal(request.method(),'PUT');server.puts++;if(server.onPut){const hook=server.onPut;server.onPut=null;await hook();}
 const data=request.postDataJSON(),expected=server.body?String(server.version).padStart(40,'0'):undefined;
 if(data.sha!==expected)return reply({},409);
 server.body=Buffer.from(data.content,'base64').toString();server.version++;
 if(server.failAfterPut){server.failAfterPut=false;return route.abort('failed');}return reply({},201);
 });
 const p=await context.newPage();await p.goto(pageOrigin);await p.getByText('С чего начнём?').waitFor();return p;
 }
 return {server,page,close:()=>browser.close()};
}
async function repo(page,command){return page.evaluate(async command=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return command?await r.dispatch(command):await r.read();}finally{r.close();}},command);}
async function sync(page){return page.evaluate(async()=>{const {openRepository}=await import('/repository.mjs'),{createGitHubClient}=await import('/github-client.mjs'),{synchronize}=await import('/sync-controller.mjs');const r=await openRepository(),client=createGitHubClient({repository:'sample-owner/private-data',token:'example-test-token'});try{await r.prepareSyncTarget(client.target.key);return await synchronize(r,client,{targetKey:client.target.key});}finally{r.close();}});}
async function form(p){await p.getByRole('button',{name:'Настройки и резервные копии'}).click();await p.locator('#sync-form [name=repository]').fill('sample-owner/private-data');await p.locator('#sync-form [name=token]').fill('example-test-token');}

test('GitHub settings check is read-only, sync backs up current data and token never persists',async()=>{
 const t=await setup();try{const p=await t.page();await repo(p,{type:'createTask',values:{title:'До обмена'}});await form(p);await p.locator('#sync-check').click();await p.getByText(/Подключение проверено:/).waitFor();assert.equal(t.server.puts,0);assert.equal((await repo(p)).sync,undefined);
 await p.locator('#sync-submit').click();await p.getByText(/Синхронизация завершена/).waitFor();assert.equal(t.server.puts,1);
 const stored=await p.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return {backup:await r.migrationBackup('github:sample-owner/private-data:main:data/state.v2.json'),exported:await r.exportBackup(),local:{...localStorage},session:{...sessionStorage}};}finally{r.close();}});
 assert.equal(stored.backup.tasks[0].title,'До обмена');assert.ok(!JSON.stringify(stored).includes('example-test-token'));assert.ok(!t.server.body.includes('example-test-token'));
 await repo(p,{type:'createTask',values:{title:'После обмена'}});await sync(p);const backup=await p.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return await r.migrationBackup('github:sample-owner/private-data:main:data/state.v2.json');}finally{r.close();}});assert.equal(backup.tasks.length,1);
 await p.reload();await p.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await p.locator('#sync-form [name=token]').inputValue(),'');assert.equal(await p.locator('#sync-form [name=repository]').inputValue(),'sample-owner/private-data');
 }finally{await t.close();}
});

test('two devices merge edits/deletions with SHA race retry and preserve local display order',async()=>{
 const t=await setup();try{const a=await t.page(),b=await t.page();const sa=await repo(a,{type:'createTask',values:{title:'A'}}),aid=sa.tasks[0].id;await sync(a);await sync(b);const sb=await repo(b,{type:'createTask',values:{title:'B'}}),bid=sb.tasks.find(x=>x.title==='B').id;
 await repo(a,{type:'updateTask',taskId:aid,values:{description:'Изменение A'}});
 t.server.onPut=()=>sync(b);await sync(a);let state=await sync(b);assert.equal(state.tasks.length,2);assert.equal(state.tasks.find(x=>x.id===aid).description,'Изменение A');assert.ok(t.server.puts>=4);
 await repo(a,{type:'reorderTask',taskId:bid,values:{targetId:aid,position:'before',view:'all',day:new Date().toISOString().slice(0,10)}});
 const order=(await repo(a)).taskOrder;await repo(a,{type:'deleteTask',taskId:aid});await sync(a);state=await sync(b);assert.equal(state.tasks.some(x=>x.id===aid),false);await sync(a);assert.equal((await repo(a)).tasks.some(x=>x.id===aid),false);assert.deepEqual((await repo(a)).taskOrder,order.filter(id=>id!==aid));
 }finally{await t.close();}
});

test('concurrent field edits retain conflicts until explicit choice; lost PUT reply is reread safely',async()=>{
 const t=await setup();try{const a=await t.page(),b=await t.page();const s=await repo(a,{type:'createTask',values:{title:'Общая'}}),id=s.tasks[0].id;await sync(a);await sync(b);
 await repo(a,{type:'updateTask',taskId:id,values:{description:'Вариант A'}});await repo(b,{type:'updateTask',taskId:id,values:{description:'Вариант B'}});await sync(a);const merged=await sync(b);const conflict=merged.sync.conflicts.find(c=>c.field==='description');assert.ok(conflict);await b.evaluate(async conflict=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{await r.resolveSync(conflict.entity,conflict.field,'Вариант B',conflict.candidates);}finally{r.close();}},conflict);await sync(b);let state=await sync(a);assert.equal(state.tasks[0].description,'Вариант B');assert.equal(state.sync.conflicts.length,0);
 t.server.failAfterPut=true;await repo(a,{type:'updateTask',taskId:id,values:{description:''}});const before=t.server.puts;await assert.rejects(sync(a),/мог сохраниться/);assert.equal(t.server.puts,before+1);await sync(a);state=await sync(b);assert.equal(state.tasks.length,1);assert.equal(state.tasks[0].description,'');
 }finally{await t.close();}
});

test('public repository, invalid document and backup quota failure never write remote data',async()=>{
 const t=await setup();try{const p=await t.page();await repo(p,{type:'createTask',values:{title:'Сохранить'}});await form(p);t.server.private=false;await p.locator('#sync-submit').click();await p.locator('#sync-error').waitFor();assert.match(await p.locator('#sync-error').textContent(),/приватный/);assert.equal(t.server.puts,0);
 t.server.private=true;t.server.body='{"version":999}';await p.locator('#sync-submit').click();await p.getByText(/Файл GitHub имеет неподдерживаемый/).waitFor();assert.equal(t.server.puts,0);assert.equal((await repo(p)).sync,undefined);
 t.server.body=null;await p.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(value,key){if(String(key).startsWith('sync-target-backup:'))throw new DOMException('test quota','QuotaExceededError');return original.apply(this,arguments);};});await p.locator('#sync-submit').click();await p.getByText(/Недостаточно места на устройстве/).waitFor();assert.equal(t.server.puts,0);assert.equal((await repo(p)).tasks[0].title,'Сохранить');
 }finally{await t.close();}
});

test('expired token and cancelled connection leave local tasks intact and unlock settings',async()=>{
 const t=await setup();try{const p=await t.page();await repo(p,{type:'createTask',values:{title:'Не потерять'}});await form(p);t.server.status=401;await p.locator('#sync-check').click();await p.getByText(/GitHub не принял токен/).waitFor();assert.equal(t.server.puts,0);
 await p.evaluate(()=>{const original=window.fetch;window.fetch=(url,options)=>String(url).startsWith('https://api.github.com/')?new Promise((resolve,reject)=>{options.signal.addEventListener('abort',()=>reject(new DOMException('Cancelled','AbortError')),{once:true});}):original(url,options);});
 await p.locator('#sync-submit').click();await p.locator('#sync-cancel').waitFor();assert.equal(await p.locator('#sync-form [name=repository]').isDisabled(),true);await p.locator('#sync-cancel').click();await p.getByText(/Обмен отменён/).waitFor();assert.equal(await p.locator('#sync-submit').isEnabled(),true);assert.equal(await p.locator('#sync-form [name=repository]').isEnabled(),true);assert.equal(t.server.puts,0);assert.equal((await repo(p)).tasks[0].title,'Не потерять');
 }finally{await t.close();}
});

test('remembered token survives reload only by opt-in, stays outside data, and can be forgotten',async()=>{
 const t=await setup();try{const p=await t.page();await repo(p,{type:'createTask',values:{title:'Локальные данные'}});await form(p);
 const token=p.locator('#sync-form [name=token]'),remember=p.locator('#sync-form [name=rememberToken]');assert.equal(await remember.isChecked(),false);
 await remember.check();await p.getByText('Токен сохранён на этом устройстве для указанного репозитория.',{exact:true}).waitFor();assert.equal(t.server.puts,0);
 await p.reload();await p.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await token.inputValue(),'example-test-token');assert.equal(await remember.isChecked(),true);
 await p.locator('#sync-submit').click();await p.getByText(/Синхронизация завершена/).waitFor();
 const data=await p.evaluate(async()=>{const {openRepository}=await import('/repository.mjs');const r=await openRepository();try{return {state:await r.read(),exported:await r.exportBackup(),backup:await r.migrationBackup('github:sample-owner/private-data:main:data/state.v2.json')};}finally{r.close();}});assert.ok(!JSON.stringify(data).includes('example-test-token'));assert.ok(!t.server.body.includes('example-test-token'));
 await remember.uncheck();assert.equal(await token.inputValue(),'example-test-token');await p.reload();await p.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await token.inputValue(),'');assert.equal(await remember.isChecked(),false);
 await token.fill('example-test-token');await remember.check();await p.locator('#sync-forget-token').click();assert.equal(await token.inputValue(),'');assert.equal(await remember.isChecked(),false);await p.reload();await p.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await token.inputValue(),'');assert.equal((await repo(p)).tasks[0].title,'Локальные данные');
 }finally{await t.close();}
});

test('device token is scoped to repository and removal propagates to another open tab',async()=>{
 const t=await setup();try{const p=await t.page();await form(p);await p.locator('#sync-form [name=rememberToken]').check();await p.getByText('Токен сохранён на этом устройстве для указанного репозитория.',{exact:true}).waitFor();
 const other=await p.context().newPage();await other.goto(p.url());await other.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await other.locator('#sync-form [name=token]').inputValue(),'example-test-token');
 await p.locator('#sync-forget-token').click();await other.waitForFunction(()=>document.querySelector('#sync-form [name=token]').value==='');assert.equal(await other.locator('#sync-form [name=rememberToken]').isChecked(),false);
 await p.locator('#sync-form [name=token]').fill('example-test-token');await p.locator('#sync-form [name=rememberToken]').check();await p.locator('#sync-form [name=repository]').fill('sample-owner/other-data');assert.equal(await p.locator('#sync-form [name=token]').inputValue(),'');assert.equal(await p.locator('#sync-form [name=rememberToken]').isChecked(),false);await p.locator('#sync-form [name=repository]').fill('sample-owner/private-data');assert.equal(await p.locator('#sync-form [name=token]').inputValue(),'example-test-token');
 }finally{await t.close();}
});

test('device token storage failure is visible and leaves task storage usable',async()=>{
 const t=await setup();try{const p=await t.page();await form(p);await p.evaluate(()=>{const set=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(String(key).startsWith('tasktimer-github-token:'))throw new DOMException('Storage unavailable','QuotaExceededError');return set.call(this,key,value);};});await p.locator('#sync-form [name=rememberToken]').check();await p.getByText(/Не удалось изменить сохранённый токен/).waitFor();assert.equal(t.server.puts,0);await repo(p,{type:'createTask',values:{title:'Работает'}});assert.equal((await repo(p)).tasks[0].title,'Работает');await p.reload();await p.getByRole('button',{name:'Настройки и резервные копии'}).click();assert.equal(await p.locator('#sync-form [name=token]').inputValue(),'');
 }finally{await t.close();}
});
