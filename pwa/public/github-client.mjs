/** GitHub Contents transport. This module never persists credentials. */
export const GITHUB_DATA_PATH='data/state.v2.json';
export const MAX_GITHUB_BYTES=1_000_000;
export class GitHubSyncError extends Error {
 constructor(code,message,status=null){super(message);this.name='GitHubSyncError';this.code=code;this.status=status;}
}
const fail=(code,message,status)=>new GitHubSyncError(code,message,status);
const validSha=value=>typeof value==='string'&&/^[a-f0-9]{40}$/i.test(value);
export function githubTarget(repository,branch='main'){
 const name=String(repository??'').trim(),ref=String(branch??'').trim();
 if(!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9_.-]{1,100}$/.test(name)||name.split('/')[1]==='.'||name.split('/')[1]==='..')throw fail('INPUT','Укажите репозиторий в формате владелец/имя, без адреса сайта.');
 if(!ref||ref.length>200||/[\s~^:?*\[\\\x00-\x1f\x7f]/.test(ref)||ref.includes('..')||ref.includes('@{')||ref.startsWith('/')||ref.endsWith('/')||ref.split('/').some(p=>!p||p.startsWith('.')||p.endsWith('.')||p.endsWith('.lock')))throw fail('INPUT','Укажите корректное имя ветки GitHub.');
 return {repository:name,branch:ref,path:GITHUB_DATA_PATH,key:`github:${name.toLowerCase()}:${ref}:${GITHUB_DATA_PATH}`};
}
function encode(text){const bytes=new TextEncoder().encode(text);if(bytes.length>MAX_GITHUB_BYTES)throw fail('SIZE','Файл синхронизации превышает 1 МБ. Обмен остановлен без перезаписи.');let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);}
function decode(content){try{const binary=atob(content.replace(/\s/g,''));if(binary.length>MAX_GITHUB_BYTES)throw fail('SIZE','Файл синхронизации превышает 1 МБ.');return new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(binary,c=>c.charCodeAt(0)));}catch(e){if(e instanceof GitHubSyncError)throw e;throw fail('BODY','GitHub вернул повреждённое содержимое файла.');}}
export async function readGitHubJson(response){
 const reader=response.body?.getReader();if(!reader)throw fail('BODY','GitHub вернул пустой ответ.');
 let length=0,text='';const decoder=new TextDecoder('utf-8',{fatal:true});
 try{while(true){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;if(length>2_000_000)throw fail('SIZE','Ответ GitHub слишком велик. Обмен остановлен.');text+=decoder.decode(value,{stream:true});}text+=decoder.decode();return JSON.parse(text);}catch(e){await reader.cancel().catch(()=>{});if(e instanceof GitHubSyncError)throw e;throw fail('BODY','Не удалось прочитать ответ GitHub. Повторите обмен после проверки сети.');}finally{reader.releaseLock();}
}
export function createGitHubClient({repository,branch='main',token,fetchImpl=globalThis.fetch}){
 const target=githubTarget(repository,branch);
 if(typeof token!=='string'||!token.trim()||/\s/.test(token))throw fail('TOKEN','Введите токен GitHub без пробелов.');
 const root=`https://api.github.com/repos/${target.repository.split('/').map(encodeURIComponent).join('/')}`;
 const endpoint=root+'/contents/'+GITHUB_DATA_PATH;
 const headers=()=>({Accept:'application/vnd.github+json',Authorization:'Bearer '+token,'X-GitHub-Api-Version':'2026-03-10'});
 async function request(url,options={}){
 let response;try{response=await fetchImpl(url,{mode:'cors',credentials:'omit',redirect:'error',cache:'no-store',...options,headers:{...headers(),...options.headers}});}catch(e){if(options.signal?.aborted||e?.name==='AbortError')throw e;throw fail('NETWORK',options.method==='PUT'?'Ответ на запись GitHub не получен. Файл мог сохраниться. Повторите синхронизацию: она сначала прочитает сервер.':'Не удалось связаться с GitHub. Проверьте сеть и повторите.');}
 if(response.redirected||response.type==='opaque'||response.type==='opaqueredirect')throw fail('REDIRECT','GitHub перенаправил запрос. Проверьте актуальное имя репозитория.');
 if(response.status===401)throw fail('AUTH','GitHub не принял токен: проверьте его срок действия и ввод.',401);
 if(response.status===403||response.status===429)throw fail('ACCESS',response.headers.get('Retry-After')||response.headers.get('X-RateLimit-Remaining')==='0'?'GitHub временно ограничил запросы. Подождите и повторите вручную.':'GitHub запретил запрос. Проверьте доступ токена к репозиторию и разрешение Contents: Read and write.',response.status);
 return response;
 }
 async function verify({signal}={}){
 const response=await request(root,{signal});if(!response.ok)throw fail('REPOSITORY','Репозиторий недоступен. Проверьте имя и доступ токена.',response.status);
 const info=await readGitHubJson(response);if(info.private!==true)throw fail('PUBLIC','Для задач нужен отдельный приватный репозиторий. Публичный репозиторий не используется.');
 const b=await request(root+'/branches/'+encodeURIComponent(target.branch),{signal});if(!b.ok)throw fail('BRANCH','Ветка недоступна. Создайте приватный репозиторий с README и проверьте имя ветки.',b.status);await b.body?.cancel();
 }
 async function read({signal}={}){
 await verify({signal});const response=await request(endpoint+'?ref='+encodeURIComponent(target.branch),{signal});if(response.status===404)return null;
 if(!response.ok)throw fail('HTTP',`GitHub: ошибка чтения HTTP ${response.status}.`,response.status);
 const file=await readGitHubJson(response);
 if(file.type!=='file'||file.path!==GITHUB_DATA_PATH||file.encoding!=='base64'||!validSha(file.sha)||typeof file.content!=='string')throw fail('BODY','GitHub не вернул обычный JSON-файл с версией SHA. Обмен остановлен.');
 if(file.size>MAX_GITHUB_BYTES)throw fail('SIZE','Файл синхронизации превышает 1 МБ.');
 return {body:decode(file.content),etag:file.sha};
 }
 return {target,label:'GitHub',read,
 async check(options){const remote=await read(options);return {exists:!!remote,remote};},
 async write(body,{etag,create=false,signal}={}){
 if(typeof body!=='string'||(create?etag!=null:!validSha(etag)))throw fail('SHA','Для записи нужна версия SHA прочитанного файла или явное создание нового файла.');
 // Recheck privacy before every write, including after the merge network gap.
 await verify({signal});
 const response=await request(endpoint,{method:'PUT',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'Sync application data',branch:target.branch,content:encode(body),...(!create?{sha:etag}:{})})});
 await response.body?.cancel();
 if(response.status===409)throw fail(412,'Файл изменился на другом устройстве. Требуется повторное чтение и объединение.',409);
 if(response.status===422)throw fail('VALIDATION','GitHub отклонил запись. Возможны изменение файла другим устройством или ограничения ветки. Повторите синхронизацию после проверки настроек.',422);
 if(!response.ok)throw fail('HTTP',`GitHub: ошибка записи HTTP ${response.status}. Данные остаются на устройстве.`,response.status);
 return {etag:null};
 }};
}
