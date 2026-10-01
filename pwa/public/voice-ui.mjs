import {VOICE_BYTES,voiceReady,installVoice,removeVoice,VoiceDictation} from './voice.mjs';

export function installVoiceInterface({confirmRemoval}) {
 const dialog=document.querySelector('#voice-dialog');
 const el=id=>document.querySelector('#voice-'+id);
 let target=null, dictation=null, installing=null, phase='idle', generation=0, ready=false;
 const status=text=>{el('status').textContent=text;};
 function controls(){
   el('download').hidden=ready;el('download').disabled=phase!=='idle';
   el('record').hidden=!target||!ready;el('record').disabled=phase!=='idle';
   el('stop').hidden=phase!=='recording';
   el('result').hidden=!target;el('add').hidden=!target;el('add').disabled=phase!=='idle'||!el('result').value.trim();
   el('remove').disabled=phase!=='idle';
 }
 function cancel(){++generation;installing?.abort();installing=null;dictation?.cancel();dictation=null;phase='idle';controls();}
 function error(error){el('error').textContent=error?.message||'Не удалось выполнить диктовку.';el('error').hidden=false;}
 async function open(input=null){cancel();target=input;el('result').value='';el('error').hidden=true;ready=false;controls();dialog.showModal();const run=generation;
  try{ready=await voiceReady();if(run!==generation)return;status(ready?'Модель готова. Запись до 60 секунд, распознавание после остановки.':`Для офлайн-диктовки загрузите модель и движок: ${(VOICE_BYTES/1000000).toFixed(1)} МБ.`);controls();}catch(e){if(run===generation)error(e);}
 }
 document.addEventListener('click',event=>{const b=event.target.closest('[data-voice-target]');if(!b)return;const input=b.closest('form')?.elements.namedItem(b.dataset.voiceTarget);if(input)open(input);});
 el('settings').addEventListener('click',()=>open());
 el('download').addEventListener('click',async()=>{
   const run=generation;installing=new AbortController();phase='installing';el('error').hidden=true;controls();
   try{await installVoice({signal:installing.signal,onProgress:({loaded,total})=>{if(run===generation)status(`Загрузка: ${Math.floor(loaded/total*100)}% (${(loaded/1000000).toFixed(1)} из ${(total/1000000).toFixed(1)} МБ)`);}});if(run!==generation)return;ready=true;status('Модель готова для офлайн-диктовки.');}
   catch(e){if(run===generation&&e.name!=='AbortError'){error(e);status('Повторите загрузку: проверенные файлы сохраняются.');}}
   finally{if(run===generation){installing=null;phase='idle';controls();}}
 });
 async function stop(){if(phase!=='recording')return;const run=generation;phase='decoding';status('Распознавание… Можно отменить.');controls();
   try{const text=await dictation.stop();if(run!==generation)return;if(text)el('result').value=[el('result').value.trim(),text].filter(Boolean).join(' ');status(text?'Проверьте текст. Можно продолжить диктовку.':'Речь не распознана. Попробуйте ещё раз.');}
   catch(e){if(run===generation&&e.name!=='AbortError')error(e);}
   finally{if(run===generation){dictation?.cancel();dictation=null;phase='idle';controls();}}
 }
 el('record').addEventListener('click',async()=>{
   const run=generation;phase='starting';el('error').hidden=true;dictation=new VoiceDictation();status('Разрешите доступ к микрофону.');controls();
   try{await dictation.start({onAutoStop:stop,onError:e=>{if(run===generation){dictation?.cancel();phase='idle';error(e);controls();}}});if(run!==generation)return;phase='recording';status('Говорите. Запись автоматически остановится через 60 секунд.');controls();}
   catch(e){if(run===generation){phase='idle';if(e.name!=='AbortError')error(e);controls();}}
 });
 el('stop').addEventListener('click',stop);
 el('result').addEventListener('input',controls);
 el('add').addEventListener('click',()=>{if(!target||phase!=='idle')return;const value=[target.value.trimEnd(),el('result').value.trim()].filter(Boolean).join(' ');if(target.maxLength>=0&&value.length>target.maxLength){error(new Error(`Текст слишком длинный: максимум ${target.maxLength} символов.`));return;}target.value=value;target.dispatchEvent(new Event('input',{bubbles:true}));dialog.close();});
 el('cancel').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',cancel);dialog.addEventListener('cancel',cancel);window.addEventListener('pagehide',cancel);
 el('remove').addEventListener('click',()=>confirmRemoval(async()=>{cancel();await removeVoice();ready=false;status('Модель удалена. Для диктовки потребуется повторная загрузка.');controls();}));
}

export function addVoiceButtons(form) {
 for(const name of ['title','description','comment']){
   const input=form.elements.namedItem(name);if(!input||form.querySelector(`[data-voice-target="${name}"]`))continue;
   const button=document.createElement('button');button.type='button';button.className='text-button';button.dataset.voiceTarget=name;button.textContent='🎙 Диктовать';button.setAttribute('aria-label',`Диктовать: ${name==='title'?'название':name==='description'?'описание':'комментарий'}`);input.insertAdjacentElement('afterend',button);
 }
}
