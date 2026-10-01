import { validateDocument } from './sync-protocol.mjs';

// Retry only conditional conflicts; never retry an ambiguous failed PUT blindly.
export async function synchronize(repository, client, { signal, attempts = 3, legacyClient, targetKey = 'default' } = {}) {
  await repository.enableSync();
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (signal?.aborted) throw signal.reason;
    const remote = await client.read({ signal });
    if (!remote && legacyClient && await repository.needsLegacyImport(targetKey)) {
      const legacy = await legacyClient.readLegacy({ signal });
      let snapshot = null;
      if (legacy) {
        try { snapshot = JSON.parse(legacy.body); }
        catch { throw new Error('Старый файл WebDAV повреждён; миграция остановлена.'); }
        if (!snapshot || typeof snapshot !== 'object' || !Array.isArray(snapshot.tasks) || ('format' in snapshot) || ('version' in snapshot && snapshot.version !== 1) || ('schemaVersion' in snapshot && snapshot.schemaVersion !== 1) || ('sync_v2' in snapshot) || ('_sync_v2' in snapshot) || ('syncDocument' in snapshot)) throw new Error('Неподдерживаемый старый формат WebDAV.');
      }
      await repository.importRemoteLegacy(snapshot, targetKey);
    }
    let document = null;
    if (remote) {
      try { document = validateDocument(JSON.parse(remote.body)); }
      catch { throw new Error('Неподдерживаемый или повреждённый файл WebDAV v2. Данные сервера не изменены.'); }
    }
    const snapshot = await repository.mergeSync(document);
    if(remote)await repository.markRemoteSeen(targetKey);
    try {
      await client.write(JSON.stringify(snapshot.document), { etag: remote?.etag, create: !remote, signal });
      // Re-read current transaction state: edits during PUT are retained locally.
      return (await repository.mergeSync(snapshot.document)).state;
    } catch (error) {
      if (error.code !== 412 || attempt === attempts - 1) throw error;
    }
  }
}
