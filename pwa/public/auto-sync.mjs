/** Scheduling only: no credentials/storage/network. Actual exchange is injected. */
export function createAutoSync({run,eligible=()=>null,onStatus=()=>{},now=()=>Date.now(),setTimer=(fn,ms)=>setTimeout(fn,ms),clearTimer=id=>clearTimeout(id),debounceMs=10_000,pollMs=120_000}){
 let enabled=false,disposed=false,busy=false,timer=null,due=null,current=null,acked=null,blocked=null,retryAt=0,failures=0,lastStarted=-Infinity;
 function status(message){onStatus(enabled?message:'Автоматическая синхронизация выключена.');}
 function clear(){if(timer!==null)clearTimer(timer);timer=null;due=null;}
 function schedule(at){
 if(!enabled||disposed)return;
 at=Math.max(at,retryAt,lastStarted+debounceMs);
 if(timer!==null&&due<=at)return;
 clear();due=at;timer=setTimer(()=>{timer=null;due=null;void tick();},Math.max(0,at-now()));
 }
 function retry(error){
 if(error?.name==='AbortError'){retryAt=now()+pollMs;status('Текущий обмен отменён.');schedule(retryAt);return;}
 if(error?.code==='RATE_LIMIT'||error?.code==='NETWORK'||Number(error?.status)>=500){
 failures++;retryAt=Math.max(now()+Math.min(300_000,30_000*2**Math.min(failures-1,4)),error.retryAt||0);
 status('Обмен отложен после ошибки. Следующая попытка: '+new Date(retryAt).toLocaleTimeString('ru-RU'));schedule(retryAt);return;
 }
 blocked=error?.message||'Проверьте настройки и выполните ручную синхронизацию.';status('Автообмен приостановлен: '+blocked);clear();
 }
 async function tick(){
 if(!enabled||disposed||busy||blocked)return;
 const reason=eligible();if(reason){status(reason);return;}
 if(now()<retryAt){schedule(retryAt);return;}
 busy=true;lastStarted=now();status('Автоматическая синхронизация…');
 try{
 const result=await run();
 if(result?.busy){status('Автообмен ждёт завершения обмена в другой вкладке.');schedule(now()+debounceMs);return;}
 if(result?.revision!==undefined){acked=result.revision;failures=0;retryAt=0;}
 status(result?.blockedReason||'Автоматический обмен выполнен.');
 }catch(error){retry(error);}
 finally{busy=false;if(enabled&&!disposed&&!blocked)schedule(Math.max(retryAt,now()+(current!==acked?debounceMs:pollMs)));}
 }
 return {
 setEnabled(value){if(enabled===!!value)return;enabled=!!value;blocked=null;failures=0;retryAt=0;clear();if(enabled)schedule(now());else status('');},
 observe(revision){if(revision===current)return;current=revision;if(enabled&&!busy&&!blocked){clear();schedule(now()+debounceMs);}},
 trigger(){if(enabled&&!blocked&&!busy)schedule(now());},
 acknowledge(revision){acked=revision;blocked=null;failures=0;retryAt=0;status('Автоматический обмен выполнен.');clear();if(enabled)schedule(now()+(current!==acked?debounceMs:pollMs));},
 failed:retry,
 reset(){blocked=null;failures=0;retryAt=0;clear();if(enabled)schedule(now()+debounceMs);},
 dispose(){disposed=true;clear();},
 };
}
