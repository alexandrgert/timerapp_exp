# WebDAV v2 — Android implementation status

Source implementation prepared; Android compilation and runtime tests have **not** been run.
Any Gradle/Actions run requires the user's separate permission. The dispatch-only
`.github/workflows/sync-pwa-check.yml` is prepared but has not been dispatched.

The same causal operation contract as desktop/PWA is in `docs/sync-v2.md`.
Android reads/writes only `<configured legacy path>.v2.json`. It reads the old
resource once when v2 does not exist, importing its task snapshot independently;
no legacy writes or unconditional PUT fallback remain. Migration is scoped to the
endpoint URL and username. The local pre-v2 file and imported remote task snapshot
are backed up. Remote UI/settings are not copied into that backup.

`data.json` is authoritative: task projection, UI, `_sync_v2`, local `_sync_actor`
and `_sync_legacy_sources` are committed together using a file lock, fsync and
atomic replacement. All production mutations reread disk inside this transaction.
Network requests run outside the transaction; response merges re-read current state.
Explicit backup restoration generates a fresh actor. Corrupt data is reported;
loading never silently replaces it with an older backup or an empty collection.

Conflicting fields retain all candidates and require a visible choice. Stale
choices and stale edit/delete confirmations are rejected without overwriting new
values. Session forms submit only changed comment/interval fields. Concurrent
active sessions remain intact until an explicit selection closes the others.
The display derives running/paused from active intervals without changing the log.
Unknown fields remain in the operation log through typed Android projection.

Transport requires HTTPS with no embedded credentials, query or fragment, rejects
redirects and checks strong ETags. Only test clients can explicitly permit loopback
HTTP. PUT uses If-Match or If-None-Match and retries 412 at most twice after refetch.
Incoming UTF-8, document bounds, causal contexts, schema and projected dates are
validated before committing or uploading. Unsupported data produces an error.

Prepared tests: nine shared protocol fixtures, migration/unknown metadata/fresh
local edits, legacy tombstone conflict and once-only import, stale session forms,
concurrent timers, explicit backup restoration, and an HTTP fixture covering 412,
concurrent edits during PUT and weak ETag rejection. These tests are **not yet run**.
Static review and `git diff --check` were completed; no APK or other package built.
