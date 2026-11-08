'use strict';
const fs=require('node:fs/promises'),path=require('node:path');
async function render(name,body){
 if(name==='github-client.mjs')return fs.readFile(path.join(__dirname,'client.mjs'));
 if(name==='index.html'){
 let s=body.toString();
 s=s.replace('Синхронизация через GitHub','Синхронизация со своим сервером').replace('Отдельный приватный репозиторий данных с README. На обоих устройствах укажите один репозиторий и ветку. Токен можно запомнить на этом устройстве; в резервную копию и обмен он не входит.','На всех устройствах откройте этот адрес. Для каждого устройства администратор выдаёт отдельный ключ доступа. Ключ можно запомнить на личном устройстве; в резервную копию и обмен он не входит.');
 s=s.replace(/<label class="field">Репозиторий данных<input[^>]+><\/label>/,'<input name="repository" type="hidden" value="local/server">').replace(/<label class="field">Ветка<input[^>]+><\/label>/,'<input name="branch" type="hidden" value="main">');
 s=s.replace('href="/guide/"','href="/server-guide/"');
 s=s.replace('Токен GitHub','Ключ устройства').replaceAll('токен','ключ').replace('Fine-grained token: доступ только к репозиторию данных, Contents: Read and write. Репозиторий приложения использовать не нужно.','Ключ даёт доступ к общей базе задач. При потере устройства отзовите его ключ на сервере.');
 return Buffer.from(s);
 }
 if(name==='app.mjs'){
 let s=body.toString().replace("`${t.repository} · ${t.branch} · ${t.path}`","`${location.origin}${t.path}`").replaceAll('приватный репозиторий, ветка и файл доступны','сервер и данные доступны').replaceAll('приватный репозиторий и ветка доступны. Файл будет создан','сервер доступен. Данные будут сохранены').replaceAll('Для этого репозитория','Для этого сервера').replaceAll('имя репозитория, ветку','адрес сервера').replaceAll('Репозиторий','Сервер').replaceAll('репозитория','сервера').replaceAll('токен','ключ').replaceAll('Токен','Ключ').replace('Доступ на GitHub при необходимости отзывается отдельно.','Доступ устройства при необходимости отзывается администратором сервера.').replace('Файл GitHub','Документ сервера').replace('tasktimer-before-github-sync.json','tasktimer-before-server-sync.json');
 return Buffer.from(s);
 }
 if(name==='release-notes.json')return fs.readFile(path.join(__dirname,'release-notes.json'));
 return body;
}
module.exports={render};
