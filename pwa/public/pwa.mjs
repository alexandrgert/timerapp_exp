const select = name => document.querySelector(`[data-pwa-${name}]`);
const status = text => { const node = select('status'); if (node) node.textContent = text; };
let registration;
let installPrompt;
let acceptedWorker = null, acceptedReloadCallbacks=[];
let noticeWorker=null, noticeRevision=null, noticeGeneration=0, applying=false;
const postponedWorkers=new WeakSet();
const dismissalKey='tasktimer-update-later:'+location.pathname;
function postponed(revision){try{return revision&&sessionStorage.getItem(dismissalKey)===revision;}catch{return false;}}
function updateError(message){status(message);const node=select('update-error');if(node){node.textContent=message;node.hidden=false;}if(select('notice'))select('notice').hidden=false;}
function workerInfo(worker){return new Promise(resolve=>{
 const channel=new MessageChannel();let timer;
 const finish=value=>{clearTimeout(timer);channel.port1.close();channel.port2.close();resolve(value);};
 channel.port1.onmessage=event=>finish(event.data);
 timer=setTimeout(()=>finish(null),2500);
 try{worker.postMessage({type:'TASKTIMER_UPDATE_INFO'},[channel.port2]);}catch{finish(null);}
});}
function validNotes(notes){return notes&&typeof notes.title==='string'&&notes.title.length>0&&notes.title.length<=150&&Array.isArray(notes.changes)&&notes.changes.length>0&&notes.changes.length<=8&&notes.changes.every(item=>typeof item==='string'&&item.length>0&&item.length<=400);}
async function showUpdate(){
 const worker=registration?.waiting, generation=++noticeGeneration;
 document.querySelectorAll('[data-pwa-update]').forEach(node=>node.hidden=!worker);
 if(!worker||!navigator.serviceWorker.controller){noticeWorker=null;if(select('notice'))select('notice').hidden=true;return;}
 if(worker===noticeWorker&&noticeRevision)return;
 if(worker!==noticeWorker&&select('update-error'))select('update-error').hidden=true;
 noticeWorker=worker;noticeRevision=null;
 if(select('release'))select('release').textContent='Новая версия готова к установке.';
 if(select('changes'))select('changes').replaceChildren();
 if(select('notice'))select('notice').hidden=postponedWorkers.has(worker);
 // Ask the waiting worker, never the active page cache or current server release.
 const info=await workerInfo(worker);
 if(generation!==noticeGeneration||registration?.waiting!==worker)return;
 noticeWorker=worker;noticeRevision=typeof info?.revision==='string'&&info.revision.length<=200?info.revision:null;
 if(select('release'))select('release').textContent=validNotes(info?.notes)?info.notes.title:'Новая версия готова к установке.';
 const list=select('changes');if(list){list.replaceChildren();for(const text of validNotes(info?.notes)?info.notes.changes:[]){const item=document.createElement('li');item.textContent=text;list.append(item);}}
 if(postponedWorkers.has(worker)&&noticeRevision){try{sessionStorage.setItem(dismissalKey,noticeRevision);}catch{}}
 if(select('notice'))select('notice').hidden=select('update-error')?.hidden!==false&&(postponedWorkers.has(worker)||postponed(noticeRevision));
}

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); installPrompt = event;
  if (select('install')) select('install').hidden = false;
});
window.addEventListener('appinstalled', () => {
  installPrompt = null; if (select('install')) select('install').hidden = true;
  status('Приложение установлено.');
});
document.addEventListener('click', async event => {
  if (event.target.closest('[data-pwa-install]') && installPrompt) {
    try { await installPrompt.prompt(); await installPrompt.userChoice; }
    catch { status('Не удалось открыть установку. Используйте меню браузера.'); }
    installPrompt = null; if (select('install')) select('install').hidden = true;
  }
  if (event.target.closest('[data-pwa-persist]')) {
    try {
      const granted = await navigator.storage?.persist?.();
      status(granted ? 'Постоянное хранение разрешено. Резервные копии всё равно нужны.' : 'Браузер не предоставил постоянное хранение. Сохраняйте резервные копии.');
    } catch { status('Не удалось запросить постоянное хранение. Сохраните резервную копию.'); }
  }
  if(event.target.closest('[data-pwa-later]')&&noticeWorker){postponedWorkers.add(noticeWorker);try{if(noticeRevision)sessionStorage.setItem(dismissalKey,noticeRevision);}catch{}if(select('notice'))select('notice').hidden=true;}
  if (event.target.closest('[data-pwa-update]') && registration?.waiting && !applying) {
    const waiting=registration.waiting;
    if (!window.confirm('Обновить приложение? Сохранённый таймер продолжит работу. Несохранённые поля формы и текст диктовки будут потеряны, запись голоса прервётся.')) return;
    const pending = [], beforeReload=[];
    window.dispatchEvent(new CustomEvent('tasktimer:before-update', {detail: {waitUntil: promise => pending.push(Promise.resolve(promise)), beforeReload: callback => beforeReload.push(callback)}}));
    if (!pending.length) {updateError('Приложение ещё не готово к обновлению. Попробуйте позже.'); return;}
    try {
      applying=true;document.querySelectorAll('[data-pwa-update]').forEach(node=>node.disabled=true);
      await Promise.all(pending);
      if(registration.waiting!==waiting){await showUpdate();updateError('Ожидающая версия изменилась. Проверьте обновление и подтвердите ещё раз.');return;}
      acceptedWorker = waiting; acceptedReloadCallbacks=beforeReload;
      waiting.postMessage({type: 'TASKTIMER_APPLY_UPDATE'});
    } catch { acceptedWorker=null;acceptedReloadCallbacks=[];updateError('Не удалось подтвердить сохранение данных. Обновление отменено.'); }
    finally{applying=false;document.querySelectorAll('[data-pwa-update]').forEach(node=>node.disabled=false);}
  }
});
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (acceptedWorker && navigator.serviceWorker.controller===acceptedWorker) {
      const callbacks=acceptedReloadCallbacks;acceptedWorker=null;acceptedReloadCallbacks=[];
      for(const callback of callbacks)callback();
      window.location.reload();
    }
    else showUpdate();
  });
  try {
    registration = await navigator.serviceWorker.register('/sw.js', {scope: '/', updateViaCache: 'none'});
    showUpdate();
    const track = worker => worker?.addEventListener('statechange', () => {
      if (worker.state === 'installed') {
        showUpdate();
        status(navigator.serviceWorker.controller ? 'Доступно обновление приложения.' : 'Приложение готово к работе без интернета.');
      }
      if (worker.state === 'redundant') status('Не удалось подготовить офлайн-версию. Повторите открытие при наличии сети.');
    });
    track(registration.installing);
    registration.addEventListener('updatefound', () => track(registration.installing));
    if (registration.active) status('Офлайн-версия сохранена на устройстве.');
    let checking=false;
    const check=async()=>{if(checking||document.visibilityState!=='visible'||!navigator.onLine)return;checking=true;try{await registration.update();await showUpdate();}catch{}finally{checking=false;}};
    document.addEventListener('visibilitychange',check);window.addEventListener('online',check);
    setInterval(check,5*60*1000);
  } catch { status('Офлайн-версия пока не сохранена. Проверьте сеть и доступное место, затем откройте приложение снова.'); }
} else {
  status('Для установки и офлайн-режима откройте приложение по HTTPS в поддерживаемом браузере.');
}
