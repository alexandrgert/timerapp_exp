// Served only by the separate self-hosted entrypoint as /github-client.mjs.
export function githubTarget(){return {repository:'local/server',branch:'main',path:'/api/sync',key:'selfhost:'+location.origin+':v2'};}
export function createGitHubClient({token,fetchImpl=globalThis.fetch}){
 if(!/^[A-Za-z0-9_-]{43}$/.test(token||''))throw Object.assign(new Error('Введите ключ устройства, выданный администратором сервера.'),{code:'AUTH'});
 const fail=(message,code,status)=>Object.assign(new Error(message),{code,status});
 async function request(options={}){
 let r;try{r=await fetchImpl('/api/sync',{mode:'same-origin',credentials:'omit',cache:'no-store',redirect:'error',...options,headers:{Authorization:'Bearer '+token,...options.headers}});}catch(e){if(e.name==='AbortError'||options.signal?.aborted)throw e;throw fail('Сервер недоступен. Данные остаются на устройстве; следующая попытка сначала прочитает сервер.','NETWORK');}
 if(r.status===401)throw fail('Ключ устройства неверен или отозван. Введите действующий ключ.','AUTH',401);
 if(r.status===403)throw fail('Сервер отклонил источник запроса. Проверьте домен сервера.','ACCESS',403);
 if(r.status===429)throw Object.assign(fail('Сервер занят. Повторите обмен после паузы.','RATE_LIMIT',429),{retryAt:Date.now()+30000});
 return r;
 }
 async function read({signal}={}){
 const r=await request({signal});if(r.status===404)return null;if(!r.ok)throw fail('Ошибка чтения сервера: '+r.status,'HTTP',r.status);
 if(!/^"[a-f0-9]{64}"$/.test(r.headers.get('etag')||''))throw fail('Сервер не вернул версию данных.','FORMAT');
 const reader=r.body.getReader(),parts=[];let size=0;try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>20*1024*1024)throw fail('Документ сервера превышает 20 МиБ.','SIZE');parts.push(value);}}catch(e){await reader.cancel().catch(()=>{});throw e;}
 const bytes=new Uint8Array(size);let i=0;for(const part of parts){bytes.set(part,i);i+=part.length;}
 return {body:new TextDecoder('utf-8',{fatal:true}).decode(bytes),etag:r.headers.get('etag')};
 }
 return {target:githubTarget(),label:'сервера',read,async check(options){const remote=await read(options);return {exists:!!remote,remote};},async write(body,{etag,create=false,signal}={}){
 if(typeof body!=='string'||new TextEncoder().encode(body).length>20*1024*1024)throw fail('Документ превышает 20 МиБ.','SIZE');
 if(create?etag!=null:!/^"[a-f0-9]{64}"$/.test(etag||''))throw fail('Для записи нужна версия прочитанного документа.','VERSION');
 const r=await request({method:'PUT',signal,headers:{'Content-Type':'application/json',...(create?{'If-None-Match':'*'}:{'If-Match':etag})},body});
 if(r.status===412)throw fail('Данные изменились; требуется повторное чтение.',412,412);
 if(!r.ok)throw fail('Сервер отклонил запись: '+r.status,r.status>=500?'HTTP':'VALIDATION',r.status);
 return {etag:r.headers.get('etag')};
 }};
}
