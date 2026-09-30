const select = name => document.querySelector(`[data-pwa-${name}]`);
const status = text => { const node = select('status'); if (node) node.textContent = text; };
let registration;
let installPrompt;
let acceptedUpdate = false;
const showUpdate = () => { if (select('update')) select('update').hidden = !registration?.waiting; };
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
  if (event.target.closest('[data-pwa-update]') && registration?.waiting) {
    if (!window.confirm('Обновить приложение? Сохранённый таймер продолжит работу. Несохранённые поля формы будут закрыты.')) return;
    const pending = [];
    window.dispatchEvent(new CustomEvent('tasktimer:before-update', {detail: {waitUntil: promise => pending.push(Promise.resolve(promise))}}));
    if (!pending.length) {status('Приложение ещё не готово к обновлению. Попробуйте позже.'); return;}
    try {
      await Promise.all(pending);
      acceptedUpdate = true;
      registration.waiting?.postMessage({type: 'TASKTIMER_APPLY_UPDATE'});
    } catch { status('Не удалось подтвердить сохранение данных. Обновление отменено.'); }
  }
});
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (acceptedUpdate) window.location.reload();
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
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') registration.update().catch(() => {});
    });
  } catch { status('Офлайн-версия пока не сохранена. Проверьте сеть и доступное место, затем откройте приложение снова.'); }
} else {
  status('Для установки и офлайн-режима откройте приложение по HTTPS в поддерживаемом браузере.');
}
