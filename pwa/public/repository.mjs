import {initialState, apply, validateBackup} from './model.mjs';

function storageError(error) {
 if(error?.name==='QuotaExceededError')return new Error('Недостаточно места на устройстве. Освободите место и повторите; данные не сброшены.');
 if(error?.name==='VersionError')return new Error('Хранилище обновлено новой версией приложения. Обновите страницу.');
 return new Error(`Не удалось прочитать или сохранить данные: ${error?.message || 'хранилище недоступно'}`);
}

export async function openRepository({name='tasktimer-pwa'}={}) {
 if(!globalThis.indexedDB)throw new Error('Браузер не предоставляет локальное хранилище IndexedDB.');
 const db=await new Promise((resolve,reject)=>{
 let settled=false;
 const request=indexedDB.open(name,1);
 request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains('state'))request.result.createObjectStore('state');};
 request.onerror=()=>{settled=true;reject(storageError(request.error));};
 request.onblocked=()=>{settled=true;reject(new Error('Закройте другие вкладки TaskTimer и повторите открытие хранилища.'));};
 request.onsuccess=()=>{if(settled)request.result.close();else{settled=true;resolve(request.result);}};
 });
 let closed=false;
 const listeners=new Set();
 let channel=null;try{if(globalThis.BroadcastChannel)channel=new BroadcastChannel(`${name}:changes`);}catch{/* Window focus still refreshes if the browser disallows channels. */}
 const notify=(state,error=null)=>{for(const fn of listeners){try{fn(state,error);}catch(e){console.error('Ошибка обновления интерфейса TaskTimer',e);}}};
 function transaction(command) {
 if(closed)return Promise.reject(new Error('Хранилище закрыто. Обновите страницу.'));
 return new Promise((resolve,reject)=>{
 let tx;try{tx=db.transaction('state','readwrite');}catch(error){reject(storageError(error));return;}
 let failure=null,result,changed=false;
 tx.onabort=()=>reject(failure||storageError(tx.error));
 tx.onerror=()=>{}; // The abort event carries the final transaction outcome.
 tx.oncomplete=()=>{
 if(changed){notify(result);try{channel?.postMessage({type:'changed'});}catch{/* A closing tab must not turn a committed write into a failure. */}}
 resolve(result);
 };
 const store=tx.objectStore('state');const request=store.get('current');
 request.onsuccess=()=>{
 try {
 // Absent key is a new database; malformed existing data must never be reset.
 const current=request.result===undefined?initialState():validateBackup(request.result);
 const reconciled=apply(current,{type:'reconcile'});
 result=validateBackup(command?apply(reconciled,command):reconciled);
 changed=request.result===undefined||JSON.stringify(result)!==JSON.stringify(current);
 if(changed)store.put(result,'current');
 }catch(error){failure=error;tx.abort();}
 };
 });
 }
 const refresh=()=>{if(!closed)transaction().then(s=>notify(s)).catch(e=>notify(undefined,e));};
 const onVisibility=()=>{if(globalThis.document?.visibilityState==='visible')refresh();};
 if(channel)channel.onmessage=refresh;
 globalThis.addEventListener?.('focus',refresh);
 globalThis.document?.addEventListener('visibilitychange',onVisibility);
 function close() {
 if(closed)return;closed=true;db.close();channel?.close();
 globalThis.removeEventListener?.('focus',refresh);globalThis.document?.removeEventListener('visibilitychange',onVisibility);listeners.clear();
 }
 db.onversionchange=()=>{notify(undefined,new Error('Хранилище обновляется в другой вкладке. Обновите страницу.'));close();};
 db.onclose=()=>{if(!closed){notify(undefined,new Error('Соединение с хранилищем прервано. Обновите страницу.'));close();}};
 return {
 read:()=>transaction(),
 dispatch:command=>{
 // Validate external import before opening a write transaction; validation is repeated on apply.
 try{if(command.type==='replaceState')command={...command,values:validateBackup(command.values)};}catch(error){return Promise.reject(error);}
 return transaction(command);
 },
 subscribe:callback=>{listeners.add(callback);return()=>listeners.delete(callback);},
 close,
 };
}
