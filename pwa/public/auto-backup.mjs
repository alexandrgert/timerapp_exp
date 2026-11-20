export function backupFilename(date=new Date()){
 const p=(n,width=2)=>String(n).padStart(width,'0');
 return `tasktimer-${date.getFullYear()}-${p(date.getMonth()+1)}-${p(date.getDate())}_${p(date.getHours())}-${p(date.getMinutes())}-${p(date.getSeconds())}-${p(date.getMilliseconds(),3)}.json`;
}
export function validateBackupSettings(value){
 if(!value||typeof value.enabled!=='boolean'||!Number.isInteger(value.minutes)||value.minutes<1||value.minutes>10080||!['downloads','folder','server'].includes(value.destination)||!Number.isFinite(value.nextAt)||value.nextAt<0)throw new Error('Некорректны настройки автокопий. Сохраните их заново.');
 return value;
}
export function createBackupScheduler({read,write,save,lock,now=()=>Date.now(),status=()=>{},paused=()=>false}){
 let busy=false,retryAt=0;
 return {async tick(){
 if(busy||paused()||now()<retryAt)return;busy=true;
 try{const pending=validateBackupSettings(await read());if(!pending.enabled||now()<pending.nextAt)return;await lock(async()=>{const config=validateBackupSettings(await read());if(paused()||!config.enabled||now()<config.nextAt)return;
 const name=backupFilename(new Date(now()));if(await save(name,config)===false)return;const at=now();await write({...config,lastAt:at,lastName:name,lastDestination:config.destination,nextAt:at+config.minutes*60000});
 status(config.destination!=='downloads'?`Копия сохранена: ${name}`:`Копия передана браузеру: ${name}. Проверьте загрузки.`);});
 }catch(error){retryAt=now()+60000;status(error.message||'Не удалось сохранить копию.');}finally{busy=false;}
 }};
}
export async function writeBackupFile(directory,name,text){
 if(await directory.queryPermission({mode:'readwrite'})!=='granted')throw new Error('Разрешите доступ к папке: откройте настройки автокопий и нажмите «Сохранить».');
 let stream;
 try{const file=await directory.getFileHandle(name,{create:true});stream=await file.createWritable();await stream.write(text);await stream.close();}catch(error){try{await stream?.abort();}catch{}throw new Error('Не удалось записать копию в папку. Проверьте доступ и свободное место.');}
}
function folderStore(scope){
 async function access(mode,handle){
 const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('tasktimer-backup-folder:'+scope,1);r.onupgradeneeded=()=>r.result.createObjectStore('settings');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction('settings',mode),store=tx.objectStore('settings');const r=mode==='readonly'?store.get('directory'):handle?store.put(handle,'directory'):store.delete('directory');let value;r.onsuccess=()=>value=r.result;tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}
 }
 return {get:()=>access('readonly'),set:handle=>access('readwrite',handle)};
}
export function installAutoBackup({exportData,download,saveServer,serverTarget,root=document}){
 const $=id=>root.querySelector('#'+id),scope=location.pathname,key='tasktimer-auto-backup:'+scope,folders=folderStore(scope);
 const defaults=()=>({enabled:false,minutes:60,destination:'downloads',nextAt:0});
 const read=()=>{const raw=localStorage.getItem(key);return raw?validateBackupSettings(JSON.parse(raw)):defaults();};
 const write=value=>localStorage.setItem(key,JSON.stringify(value));
 const status=text=>{$('backup-auto-status').textContent=text;};
 let selectedDirectory=null,pendingDestination=null,dirty=false,pickerBusy=false;
 function render(){try{const config=read();if(!dirty){$('backup-auto-enabled').checked=config.enabled;$('backup-auto-minutes').value=config.minutes;$('backup-storage').value=config.destination==='server'?'server':'device';}
 const destination=pendingDestination||config.destination;$('backup-device-controls').hidden=destination==='server';$('backup-server-help').hidden=destination!=='server';$('backup-auto-destination').textContent=destination==='server'?'Приватный репозиторий из настроек синхронизации → backups/':destination==='folder'?`Папка: ${selectedDirectory?.name||'выбранная ранее'}`:'Папка загрузок браузера';$('backup-use-downloads').hidden=destination!=='folder';
 $('backup-auto-last').textContent=config.lastAt?`${(config.lastDestination||config.destination)!=='downloads'?'Последняя копия':'Последняя отправка в загрузки'}: ${new Date(config.lastAt).toLocaleString('ru-RU')}`:'Автоматических копий ещё нет.';
 }catch(error){status(error.message);}}
 $('backup-choose-folder').hidden=typeof globalThis.showDirectoryPicker!=='function';
 const scheduler=createBackupScheduler({read,write,paused:()=>pickerBusy,save:async(name,config)=>{const backup=await exportData();const text=JSON.stringify(backup,null,2);if(pickerBusy)return false;
 if(config.destination==='server'){if(!saveServer)throw new Error('Серверное хранение недоступно в этой версии.');await saveServer(name,text,config);}else if(config.destination==='folder'){const directory=await folders.get();if(!directory)throw new Error('Папка недоступна. Выберите её повторно в настройках автокопий.');await writeBackupFile(directory,name,text);}else download(text,name);
 },lock:async action=>{if(!navigator.locks?.request)throw new Error('Браузер не поддерживает безопасные автокопии. Используйте «Скачать JSON».');return navigator.locks.request('tasktimer-auto-backup:'+scope,{ifAvailable:true},lock=>lock?action():undefined);},status:text=>{status(text);render();}});
 $('backup-storage').addEventListener('change',()=>{pendingDestination=$('backup-storage').value==='server'?'server':'downloads';dirty=true;render();});
 $('backup-choose-folder').addEventListener('click',async()=>{
 if(pickerBusy)return;pickerBusy=true;$('backup-choose-folder').disabled=true;$('backup-auto-save').disabled=true;
 try{
 // Keep user activation: invoke the native picker directly from this click, before any await.
 const directory=await globalThis.showDirectoryPicker({mode:'readwrite',id:'tasktimer-backups'});
 selectedDirectory=directory;pendingDestination='folder';dirty=true;render();status('Папка выбрана. Сохраните настройки.');
 }catch(error){status(error.name==='AbortError'?'Выбор папки не завершён. Если окно закрылось само, проверьте обновления Chrome. Попробуйте уменьшить окно выбора, чтобы оно не перекрывало приложение целиком. Прежнее место сохранения не изменено.':error.name==='SecurityError'?'Браузер не разрешил выбор папки. Откройте PWA отдельным окном или вкладкой и нажмите «Выбрать папку» повторно.':'Не удалось выбрать папку. Можно сохранять в загрузки браузера.');}
 finally{pickerBusy=false;$('backup-choose-folder').disabled=false;$('backup-auto-save').disabled=false;}
 });
 $('backup-use-downloads').addEventListener('click',()=>{pendingDestination='downloads';selectedDirectory=null;dirty=true;render();});
 for(const id of ['backup-auto-enabled','backup-auto-minutes'])$(id).addEventListener('input',()=>dirty=true);
 $('backup-auto-form').addEventListener('submit',async event=>{event.preventDefault();const button=$('backup-auto-save');button.disabled=true;
 try{const old=read(),enabled=$('backup-auto-enabled').checked,minutes=Number($('backup-auto-minutes').value),destination=pendingDestination||old.destination;
 validateBackupSettings({...old,enabled,minutes,destination,nextAt:Date.now()+minutes*60000});
 if(enabled&&!navigator.locks?.request)throw new Error('Браузер не поддерживает безопасные автокопии. Используйте «Скачать JSON».');
 if(destination==='folder'&&enabled){const directory=selectedDirectory||await folders.get();if(!directory)throw new Error('Выберите папку для копий.');if(await directory.requestPermission({mode:'readwrite'})!=='granted')throw new Error('Нет разрешения на запись в папку. Выберите её повторно.');}
 const target=destination==='server'?serverTarget?.():undefined;if(destination==='server'&&!target)throw new Error('Укажите репозиторий, ветку и токен в настройках синхронизации.');
 const persist=async()=>{const latest=read();if(destination==='folder'&&selectedDirectory)await folders.set(selectedDirectory);else if(destination==='downloads'&&latest.destination==='folder')await folders.set(null);write({...latest,enabled,minutes,destination,serverTarget:target,nextAt:Date.now()+minutes*60000});};
 if(navigator.locks?.request)await navigator.locks.request('tasktimer-auto-backup:'+scope,persist);else await persist();
 dirty=false;pendingDestination=null;render();status(enabled?`Автокопии включены. Первая копия через ${minutes} мин. При закрытой PWA расписание не выполняется.`:'Автокопии выключены.');
 }catch(error){status(error.message||'Не удалось сохранить настройки автокопий.');}finally{button.disabled=false;}});
 const timer=setInterval(()=>void scheduler.tick(),10000);
 const wake=()=>{if(pickerBusy)return;render();void scheduler.tick();};document.addEventListener('visibilitychange',wake);window.addEventListener('focus',wake);window.addEventListener('storage',event=>{if(event.key===key){dirty=false;pendingDestination=null;render();}});
 try{if(read().destination==='folder')void folders.get().then(handle=>{if(!dirty&&!selectedDirectory)selectedDirectory=handle;render();}).catch(()=>status('Папка недоступна. Выберите её повторно.'));}catch{}
 render();void scheduler.tick();
 return {dispose(){clearInterval(timer);document.removeEventListener('visibilitychange',wake);window.removeEventListener('focus',wake);}};
}
