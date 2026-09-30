# TaskTimer WebDAV v2 protocol

Status: engine and shared fixtures; platform integration must be verified separately.

Remote resource is configured legacy path **plus `.v2.json`** (example `tasks.json.v2.json`). Never write the legacy file. First import preserves an untouched backup. Unsupported format/version stops exchange without changing either copy.

Envelope: `{"format":"tasktimer-sync","version":2,"ops":[]}`. An operation is:

```json
{"actor":"uuid-device","seq":1,"seen":{},"entity":["task","task-id"],"changes":{"$alive":true,"title":"Example"}}
```

Session entity is `["session","task-id","session-id"]`. IDs and dates retain original strings. Actor is ASCII `[A-Za-z0-9_.:-]{1,160}` excluding prototype names. Each actor has a contiguous positive integer sequence (maximum JavaScript safe integer). Actor IDs are installation-specific, persisted and never shared through backup restores. `seen` is the vector of maximum observed operation sequences before this operation; omit zero entries. It includes actor's own previous sequence. Every referenced predecessor and its transitive context must be present. Reject gaps, cycles and colliding unequal operations at the same dot `(actor, seq)`.

Each ordinary edit has `$alive:true`; deletion has `$alive:false`. A field-only conflict resolution omits `$alive` to leave lifecycle candidates unchanged. Session edits/deletions also append a parent task `$alive:true` operation with the now-current context. This makes concurrent parent deletion and session edits visible as lifecycle conflict. Adapters must not permit editing hidden deleted entities except explicit restoration.

All task fields except `id` and `sessions` are separate atomic registers. All session fields except `id` and the interval fields are separate registers. Session `started_at`, `ended_at`, and optional `duration_seconds` are stored together in register `interval`, containing their original field names. Editing one time requires sending the whole current interval. The interval must be an object containing only those three keys; embedded IDs/prototype keys are rejected. Unknown JSON fields and operation extensions survive; reserved field names `id`, `sessions`, `__proto__`, `constructor`, `prototype` are rejected. Values may be null, empty strings, arrays or objects. NaN/infinities/non-JSON values are rejected. Missing optional fields in an adapter are not erasures: explicitly write null when intended. Envelope extensions must agree if both copies contain them, otherwise fail without writing.

Merge is union by dot, with exact canonical JSON equality for repeated dots. Output operations sort lexicographically by canonical JSON `[actor,seq]`, using ASCII actor IDs. Wire JSON need not be byte-identical. Equality is recursive structural JSON equality: object key order is irrelevant, array order matters, booleans are distinct from numbers, and finite numbers compare as IEEE-754 binary64 values (1 equals 1.0). Object/entity/field ordering uses Unicode scalar-value lexicographic order; unpaired surrogates are rejected. Dot ordering uses compact JSON [ASCII actor, integer seq], therefore does not depend on number formatting of field values. The JS canonical helper is local serialization, not a cross-language equality algorithm. No wall-clock ordering, length heuristic or tombstone expiry. A field's live candidates are writes not observed by another write **to that field**. Equal candidate values coalesce, retaining all dots. Unequal candidates are conflicts. For provisional display each candidate dots list is sorted by dot; candidates sort by their smallest dot; first is displayed, except any maximal `$alive:false` hides the entity. No losing value is discarded.

Conflict resolution requires selecting one currently retained candidate and writing its value in a new operation that observes the entire current log. Resolving a non-lifecycle field writes only that field (no parent touch), preserving lifecycle candidates; a lifecycle restore must explicitly select true. UI lists entity/field/candidates and never describes provisional display as resolved. Concurrent timer starts can create multiple active sessions; adapters must preserve them and request resolution rather than silently dropping/closing activity.

Migration: `importLegacy(tasks, freshMigrationActor)` creates a self-contained log from an unsynced legacy snapshot with empty initial context. Merge this independent log with v2; do NOT record legacy differences as new writes observing v2, which would silently override deletions. Persist migration completion with v2/local tasks in one transaction. A second legacy import is not automatic. Differing legacy values remain conflicts, including old present rows against v2 tombstones. Missing legacy rows alone cannot prove deletion and do not delete remote data.

Transport: GET with strong ETag; conditional PUT `If-Match:<etag>` or creation `If-None-Match:*`. Missing strong ETag on an existing resource is an explicit error. 412 means bounded refetch/merge/retry. Network outside local transaction; on return merge with latest local state inside transaction so local concurrent edits survive. One operation log and projection are committed atomically. No unsafe unconditional fallback. Do not print credentials or include them in exports.

Safety bounds: 20,000 operations and 20 MiB UTF-8 canonical envelope. Exceeding either stops safely with a user-visible error; no automatic truncation/compaction. This initial protocol retains history; future compaction requires a separately versioned design.

## JavaScript API

- `emptyDocument()` -> envelope
- `validateDocument(doc)` -> defensive canonical deep copy or throws
- `mergeDocuments(a,b)` -> envelope
- `changeEntity(doc,actor,entity,changes)` -> envelope, session edits touch parent
- `projectDocument(doc)` -> `{entities:[{entity,deleted,values}],conflicts:[{entity,field,candidates:[{value,dots:[[actor,seq]]}]}]}`
- `resolveConflict(doc,actor,entity,field,value)` -> envelope
- `importLegacy(tasks,actor)` -> independent envelope
- `reconcileTasks(doc,beforeTasks,afterTasks,actor)` -> envelope; caller supplies current transaction snapshot
- `projectTasks(doc)` -> `{tasks,conflicts}`; visible tasks/sessions preserve unknown fields
- `remoteV2Path(legacyPath)` -> suffixed path
- `canonical(value)` -> deterministic JSON string

Fixtures in `tests/fixtures/sync-v2/cases.json` include inputs and independently inspected expected projections; Python/Kotlin should assert the same merge and conflict semantics. Engine does not validate app-specific calendar/status invariants; application adapters must validate these and retain incompatible concurrent versions for explicit resolution.
