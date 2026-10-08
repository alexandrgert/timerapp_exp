/** Direct browser transport. Credentials remain in this instance only. */
export const MAX_WEBDAV_BYTES = 32 * 1024 * 1024;
export class WebDavError extends Error {
  constructor(code, message, status = null) { super(message); this.name = 'WebDavError'; this.code = code; this.status = status; }
}
const strongETag = value => typeof value === 'string' && /^"[\x21\x23-\x7e\x80-\xff]*"$/.test(value);
const fail = (code, message, status) => new WebDavError(code, message, status);

/** Resolve the original data file; v2 remains a separate resource beside it. */
export function resolveWebDavUrls(server, filePath='') {
 let base;try{base=new URL(String(server).trim());}catch{throw fail('URL','Укажите полный HTTPS-адрес сервера или файла WebDAV.');}
 if(base.protocol!=='https:'||base.username||base.password||base.search||base.hash)throw fail('URL','Нужен HTTPS-адрес без логина, пароля, параметров и фрагмента #.');
 if(base.hostname==='cloudbeeline.ru')throw fail('URL','Это веб-интерфейс облака. Для WebDAV Билайна используйте https://webdav.cloudbeeline.ru и путь tasktimer/data.json.');
 const path=String(filePath).trim();
 if(path){
 if(/\.json$/i.test(base.pathname))throw fail('URL','Указан полный адрес файла. Очистите отдельное поле пути или оставьте в адресе только сервер.');
 if(/[?#\\]/.test(path)||/^[a-z][a-z0-9+.-]*:/i.test(path)||path.startsWith('//'))throw fail('URL','Путь должен быть относительным, например tasktimer/data.json.');
 const relative=path.replace(/^\//,'');
 const segments=relative.split('/');
 try{if(segments.some(part=>{const decoded=decodeURIComponent(part);return !decoded||decoded==='.'||decoded==='..'||/[\/\\?#]/.test(decoded);}))throw new Error();}catch{throw fail('URL','Некорректный путь к файлу WebDAV.');}
 base.pathname=base.pathname.replace(/\/?$/,'/')+relative;
 }
 if(!/\.json$/i.test(base.pathname))throw fail('URL','Укажите путь к файлу JSON, например tasktimer/data.json, либо полный адрес этого файла.');
 if(/(?:\.v2|\.sync-meta)\.json$/i.test(base.pathname))throw fail('URL','Укажите исходный файл data.json, а не data.json.v2.json или data.sync-meta.json. Файл v2 выбирается автоматически.');
 const legacyUrl=base.href;base.pathname+='.v2.json';return {legacyUrl,url:base.href};
}

/** url is the exact v2 resource URL; caller derives it with resolveWebDavUrls. */
export function createWebDavClient({ url, username = '', password = '', fetchImpl = globalThis.fetch }) {
  let endpoint;
  try { endpoint = new URL(url); } catch { throw fail('URL', 'Укажите полный HTTPS-адрес файла WebDAV.'); }
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.hash) {
    throw fail('URL', 'WebDAV требует HTTPS без пароля в адресе и без фрагмента #.');
  }
  if (typeof username !== 'string' || typeof password !== 'string' || username.includes(':') || /[\r\n]/.test(username + password)) {
    throw fail('AUTH_INPUT', 'Некорректное имя пользователя или пароль WebDAV.');
  }
  const bytes = new TextEncoder().encode(`${username}:${password}`);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const authorization = username || password ? `Basic ${btoa(binary)}` : null;
  const headers = () => ({ Accept: 'application/json', ...(authorization ? { Authorization: authorization } : {}) });
  async function request(method, options = {}) {
    let response;
    try {
      response = await fetchImpl(endpoint.href, { method, mode: 'cors', credentials: 'omit', redirect: 'error', cache: 'no-store', ...options });
    } catch (error) {
      if (options.signal?.aborted || error?.name === 'AbortError') throw error;
      throw fail('NETWORK_CORS', 'Браузер не смог выполнить запрос WebDAV. Возможны недоступность сети, перенаправление или запрет CORS; это не подтверждает ошибку пароля. Сервер должен отвечать на предварительный OPTIONS без авторизации, разрешать адрес приложения, GET/PUT и заголовки Authorization, Content-Type, If-Match, If-None-Match, а также открывать ETag через Access-Control-Expose-Headers. Успешное подключение desktop не проверяет CORS.');
    }
    if (response.redirected || response.type === 'opaque' || response.type === 'opaqueredirect') throw fail('REDIRECT', 'WebDAV должен отвечать напрямую без перенаправления.');
    return response;
  }
  async function readFile({ signal } = {}, requireETag = true) {
      const response = await request('GET', { headers: headers(), signal });
      if (response.status === 404) return null;
      if (!response.ok) throw fail('HTTP', `WebDAV: ошибка чтения HTTP ${response.status}.`, response.status);
      const etag = response.headers.get('ETag');
      if (requireETag && !strongETag(etag)) {
        await response.body?.cancel();
        throw fail('ETAG', 'WebDAV не вернул сильный ETag. Нужны сильные ETag и Access-Control-Expose-Headers: ETag; без них безопасная синхронизация невозможна.');
      }
      if (Number(response.headers.get('Content-Length')) > MAX_WEBDAV_BYTES) {
        await response.body?.cancel();
        throw fail('SIZE', 'Файл WebDAV превышает 32 МиБ.');
      }
      const reader = response.body?.getReader();
      if (!reader) throw fail('BODY', 'WebDAV вернул пустой ответ вместо JSON.');
      const decoder = new TextDecoder('utf-8', { fatal: true });
      let body = '', size = 0;
      try {
        while (true) {
          if (signal?.aborted) throw signal.reason || new DOMException('Операция отменена', 'AbortError');
          const { value, done } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > MAX_WEBDAV_BYTES) throw fail('SIZE', 'Файл WebDAV превышает 32 МиБ.');
          body += decoder.decode(value, { stream: true });
        }
        body += decoder.decode();
      } catch (error) {
        await reader.cancel().catch(() => {});
        if (signal?.aborted || error?.name === 'AbortError' || error instanceof WebDavError) throw error;
        throw fail('BODY', 'Не удалось прочитать JSON WebDAV: ответ повреждён или соединение прервано.');
      } finally { reader.releaseLock(); }
      return { body, etag };
  }
  return {
    async write(body, { etag, create = false, signal } = {}) {
      if ((create && etag != null) || (!create && !strongETag(etag))) throw fail('ETAG', 'Для записи нужна точная версия ETag или явное создание нового файла.');
      if (typeof body !== 'string') throw fail('BODY', 'WebDAV принимает сериализованный JSON.');
      if (new TextEncoder().encode(body).byteLength > MAX_WEBDAV_BYTES) throw fail('SIZE', 'Файл WebDAV превышает 32 МиБ.');
      const response = await request('PUT', { signal, body, headers: {
        ...headers(), 'Content-Type': 'application/json; charset=utf-8',
        ...(create ? { 'If-None-Match': '*' } : { 'If-Match': etag }),
      } });
      await response.body?.cancel();
      if (response.status === 412) throw fail(412, 'Файл изменён другим устройством. Требуется повторное чтение и объединение.', 412);
      if (!response.ok) throw fail('HTTP', `WebDAV: ошибка записи HTTP ${response.status}.`, response.status);
      const next = response.headers.get('ETag');
      return { etag: strongETag(next) ? next : null };
    },
    read: options => readFile(options),
    readLegacy: options => readFile(options, false),
  };
}
