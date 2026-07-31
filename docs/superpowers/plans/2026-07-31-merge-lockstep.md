# Q1: Merge Lockstep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Desktop и Android при WebDAV merge выбирают одну и ту же сессию при конфликте одного `session.id`, с сохранением `comment` / `bitrix_record_id`.

**Architecture:** Единое правило richer-session на обеих платформах; общие JSON-фикстуры; документация приводится к коду (union sessions по id). Эталон алгоритма — текущий Android meta-score + явный tie-break.

**Tech Stack:** Python 3.12 / pytest (`src/timerapp_ag/domain/merge.py`); Kotlin / JUnit (`android/.../data/DataMerge.kt`); fixtures JSON.

## Global Constraints

- Версия в `pyproject.toml` не бампать в этом плане (только merge + docs + tests); bump — при локальной сборке deb по запросу.
- Секреты WebDAV/Bitrix не трогать.
- Локально APK не собирать (правило local-build-deb-only).
- Не менять UI merge / UI-from-richest-file в этом плане (только session pick + docs + tests).

---

## Chosen algorithm (lockstep)

Для двух `Session` с одним `id`:

1. Если у одной есть `ended_at`, а у другой нет → взять **закрытую**.
2. Иначе сравнить длительность (секунды) → взять **большую**.
3. Иначе `session_meta_score`: `+2` если `bitrix_record_id` непустой, `+1` если `comment` непустой → взять **больший score**.
4. При равном score → взять **candidate** (второй аргумент / позже в обходе `left.sessions + right.sessions`).

Сейчас: Python делает шаги 1–2 и на равной длительности всегда `candidate` **без** meta → может отбросить Bitrix id с Android. Android делает 1–3, но при равном meta оставляет `existing` → расходится с Python на шаге 4.

---

## File map

| File | Role |
|------|------|
| [`src/timerapp_ag/domain/merge.py`](src/timerapp_ag/domain/merge.py) | Добавить `_session_meta_score`, обновить `_pick_richer_session` |
| [`android/.../data/DataMerge.kt`](android/app/src/main/java/com/timerapp/linkb24/data/DataMerge.kt) | Tie-break: при равном meta → `candidate` |
| [`tests/fixtures/merge_lockstep/`](tests/fixtures/merge_lockstep/) | Create: golden JSON pairs |
| [`android/app/src/test/resources/merge_lockstep/`](android/app/src/test/resources/merge_lockstep/) | Копия тех же fixtures |
| [`tests/test_merge_lockstep.py`](tests/test_merge_lockstep.py) | Create: pytest по fixtures + unit meta |
| [`android/.../data/DataMergeTest.kt`](android/app/src/test/java/com/timerapp/linkb24/data/DataMergeTest.kt) | Тесты meta + fixture loader |
| [`docs/webdav-sync.md`](docs/webdav-sync.md) | Исправить описание merge / ограничений |
| [`ИНСТРУКЦИЯ.md`](ИНСТРУКЦИЯ.md) | Согласовать формулировку про потерю интервалов (только same-id conflict) |

---

### Task 1: Failing tests for session meta + tie-break (Python)

**Files:**
- Create: `tests/test_merge_lockstep.py`
- Modify: (none yet)

**Interfaces:**
- Consumes: `merge_task_pair`, `Session`, `Task` from existing models
- Produces: tests that encode the chosen algorithm

- [x] **Step 1: Write failing test — equal duration prefers bitrix_record_id**

```python
def test_pick_richer_session_prefers_bitrix_record_when_duration_equal() -> None:
    left = Task(
        id="t1", day="2026-07-30", title="T", status=TaskStatus.PAUSED,
        created_at="2026-07-30T10:00:00+03:00",
        sessions=[
            Session(
                id="s1",
                started_at="2026-07-30T10:00:00+03:00",
                ended_at="2026-07-30T11:00:00+03:00",
                comment="",
                bitrix_record_id=None,
            ),
        ],
    )
    right = Task(
        id="t1", day="2026-07-30", title="T", status=TaskStatus.PAUSED,
        created_at="2026-07-30T10:00:00+03:00",
        sessions=[
            Session(
                id="s1",
                started_at="2026-07-30T10:00:00+03:00",
                ended_at="2026-07-30T11:00:00+03:00",
                comment="",
                bitrix_record_id="42",
            ),
        ],
    )
    merged = merge_task_pair(left, right)
    assert merged.sessions[0].bitrix_record_id == "42"
```

- [x] **Step 2: Write failing test — equal duration+meta prefers comment on richer side; equal everything prefers candidate (right)**

```python
def test_pick_richer_session_prefers_comment_then_candidate_on_full_tie() -> None:
    # comment wins over empty
    ...
    # both empty comment/bitrix, same times: right (candidate) wins
    merged = merge_task_pair(left, right)
    assert merged.sessions[0].comment == right.sessions[0].comment  # or marker field
```

(В полном тесте использовать разный `comment` только на candidate при нулевом meta на existing — для full tie сравнивать стабильный маркер, например разный whitespace-stripped empty vs использовать started_at identical и проверять что победила копия с `bitrix_record_id` уже покрыта; для full tie: existing comment="", candidate comment="" — результат должен быть объект candidate; проверить через уникальный не-мета признак нельзя без различия — при полном равенстве полей assert identity of fields is enough that merge is deterministic: `merge_task_pair(left,right)==merge_task_pair(left,right)` and `merge_task_pair(A,B)` session equals B's session when A and B differ only in field not used for scoring… Use `comment="a"` vs `comment="b"` both score +1: tie on meta → candidate wins → `"b"` if B is right.)

```python
def test_equal_meta_comment_prefers_candidate() -> None:
    left_s = Session(id="s1", started_at="2026-07-30T10:00:00+03:00",
                     ended_at="2026-07-30T11:00:00+03:00", comment="a")
    right_s = Session(id="s1", started_at="2026-07-30T10:00:00+03:00",
                      ended_at="2026-07-30T11:00:00+03:00", comment="b")
    merged = merge_task_pair(_task_with(left_s), _task_with(right_s))
    assert merged.sessions[0].comment == "b"
```

- [x] **Step 3: Run tests — expect FAIL**

Run: `cd /home/alex/cursorai/project/github/timerapp_exp && .venv/bin/pytest tests/test_merge_lockstep.py -v`

Expected: FAIL — bitrix id lost / comment `"a"` kept (current Python ignores meta; returns candidate only when seconds equal so comment test might already pass for candidate; **bitrix test fails** because existing processed first then candidate without bitrix wins if candidate is left without bitrix… Order left then right: existing=no bitrix, candidate=with bitrix, seconds equal → Python returns candidate → bitrix kept! So swap order:

```python
# critical: right WITHOUT bitrix, left WITH bitrix — merge left+right
# iteration: first left (has bitrix), then right (no bitrix) → candidate=right replaces if seconds equal
merged = merge_task_pair(with_bitrix, without_bitrix)
assert merged.sessions[0].bitrix_record_id == "42"  # must KEEP left's bitrix
```

This fails on current Python (returns candidate without bitrix).

- [x] **Step 4: Commit tests only** (skipped — no commit unless user asks)

```bash
git add tests/test_merge_lockstep.py
git commit -m "test: lockstep merge prefers session bitrix/comment meta"
```

---

### Task 2: Implement Python `_session_meta_score` + `_pick_richer_session`

**Files:**
- Modify: `src/timerapp_ag/domain/merge.py` (`_pick_richer_session` ~17–26)

**Interfaces:**
- Produces: `_session_meta_score(session: Session) -> int`; updated `_pick_richer_session`

- [x] **Step 1: Implement**

```python
def _session_meta_score(session: Session) -> int:
    score = 0
    if (session.comment or "").strip():
        score += 1
    if session.bitrix_record_id and str(session.bitrix_record_id).strip():
        score += 2
    return score


def _pick_richer_session(existing: Session, candidate: Session) -> Session:
    if existing.ended_at and not candidate.ended_at:
        return existing
    if candidate.ended_at and not existing.ended_at:
        return candidate
    existing_seconds = duration_seconds(existing.started_at, existing.ended_at)
    candidate_seconds = duration_seconds(candidate.started_at, candidate.ended_at)
    if candidate_seconds != existing_seconds:
        return candidate if candidate_seconds > existing_seconds else existing
    existing_meta = _session_meta_score(existing)
    candidate_meta = _session_meta_score(candidate)
    if candidate_meta != existing_meta:
        return candidate if candidate_meta > existing_meta else existing
    return candidate
```

- [x] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_merge_lockstep.py tests/test_merge_equivalence.py -v`

Expected: PASS

- [x] **Step 3: Commit**

```bash
git add src/timerapp_ag/domain/merge.py
git commit -m "fix(merge): prefer session bitrix/comment when durations tie"
```

---

### Task 3: Align Android `pickRicherSession` tie-break

**Files:**
- Modify: `android/app/src/main/java/com/timerapp/linkb24/data/DataMerge.kt` (`pickRicherSession` ~103–118)
- Modify: `android/app/src/test/java/com/timerapp/linkb24/data/DataMergeTest.kt`

**Interfaces:**
- Consumes: existing `sessionMetaScore`
- Produces: same 4-step algorithm as Python

- [x] **Step 1: Write failing Kotlin test (equal meta comments → candidate)**

```kotlin
@Test
fun pickRicherSession_equalMetaPrefersCandidate() {
    val left = TaskDto(
        id = "t1", day = "2026-07-30", title = "T",
        createdAt = "2026-07-30T10:00:00+03:00",
        sessions = listOf(
            SessionDto("s1", "2026-07-30T10:00:00+03:00", "2026-07-30T11:00:00+03:00", comment = "a"),
        ),
    )
    val right = TaskDto(
        id = "t1", day = "2026-07-30", title = "T",
        createdAt = "2026-07-30T10:00:00+03:00",
        sessions = listOf(
            SessionDto("s1", "2026-07-30T10:00:00+03:00", "2026-07-30T11:00:00+03:00", comment = "b"),
        ),
    )
    assertEquals("b", mergeTaskPair(left, right).sessions.single().comment)
}
```

Expected FAIL on current Android (`>` keeps `"a"`).

- [x] **Step 2: Change pickRicherSession final lines to**

```kotlin
val existingMeta = sessionMetaScore(existing)
val candidateMeta = sessionMetaScore(candidate)
if (candidateMeta != existingMeta) {
    return if (candidateMeta > existingMeta) candidate else existing
}
return candidate
```

- [x] **Step 3: Add test bitrix survives when candidate lacks it** (mirror Python order)

- [x] **Step 4: Run**

Run: `android/gradlew -p android app:testDebugUnitTest --tests com.timerapp.linkb24.data.DataMergeTest`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/timerapp/linkb24/data/DataMerge.kt \
  android/app/src/test/java/com/timerapp/linkb24/data/DataMergeTest.kt
git commit -m "fix(android): align session merge tie-break with desktop"
```

---

### Task 4: Shared golden fixtures

**Files:**
- Create: `tests/fixtures/merge_lockstep/README.md` (one paragraph: keep android copy in sync)
- Create: `tests/fixtures/merge_lockstep/case_bitrix_vs_plain/{left.json,right.json,expected_session.json}`
- Create: `tests/fixtures/merge_lockstep/case_comment_tie/{left.json,right.json,expected_session.json}`
- Create: `tests/fixtures/merge_lockstep/case_union_two_ids/{left.json,right.json,expected_task.json}`
- Create: identical tree under `android/app/src/test/resources/merge_lockstep/`

JSON shape: minimal `AppDataDto` / task fragments with snake_case keys matching `data.json` (`bitrix_record_id`, `started_at`, …).

- [x] **Step 1: Author 3 fixture cases** covering bitrix keep, comment tie → candidate, union two session ids

- [x] **Step 2: Python loader test** parametrize over case dirs; `merge_task_pair` / `merge_states`; assert expected session/task fields

- [x] **Step 3: Kotlin loader** read classpath `merge_lockstep/...`; decode with `AppJson`; assert same

- [x] **Step 4: Run both suites**

- [x] **Step 5: Commit**

```bash
git add tests/fixtures/merge_lockstep android/app/src/test/resources/merge_lockstep \
  tests/test_merge_lockstep.py android/app/src/test/java/com/timerapp/linkb24/data/DataMergeTest.kt
git commit -m "test: shared merge_lockstep golden fixtures"
```

---

### Task 5: Docs — webdav-sync + инструкция

**Files:**
- Modify: `docs/webdav-sync.md` § merge algorithm (L21–24) and § Ограничения (L39–41)
- Modify: `ИНСТРУКЦИЯ.md` only if it still says whole-task win without union

**Correct text (intent):**
- При совпадении task `id`: **union sessions по session id**; при конфликте одного session id — richer-session (ended → duration → meta bitrix/comment → candidate).
- Метаданные задачи (title/status/…) — от более «богатой» копии (`task_richer`), с доп. правилами status/completed/result/priorities как в коде.
- Ограничение: при **одном** session id и разных интервалах/метаданных побеждает одна версия сессии; не запускать одну задачу одновременно на двух устройствах.

- [x] **Step 1: Edit docs**
- [x] **Step 2: Commit**

```bash
git add docs/webdav-sync.md ИНСТРУКЦИЯ.md
git commit -m "docs: describe session union merge for WebDAV"
```

---

### Task 6: Verification gate

- [x] **Step 1: Python**

Run: `.venv/bin/pytest tests/test_merge_lockstep.py tests/test_merge_equivalence.py -q`

Expected: all PASS

- [x] **Step 2: Android**

Run: `"/home/alex/cursorai/project/github/timerapp_exp/android/gradlew" -p android app:testDebugUnitTest --tests 'com.timerapp.linkb24.data.DataMergeTest'`

Expected: BUILD SUCCESSFUL

- [x] **Step 3: Self-check vs roadmap Q1**
  - Meta score on both platforms
  - Tie-break candidate
  - Golden fixtures both sides
  - Docs match union-by-id

---

## Spec coverage (self-review)

| Roadmap Q1 item | Task |
|-----------------|------|
| Align richer-session | Task 2–3 |
| Golden fixtures cross-test | Task 4 |
| Fix webdav-sync.md | Task 5 |

No placeholders left. Types: `Session.bitrix_record_id`, `Session.comment` already on desktop models.

## Execution

Plan saved at `docs/superpowers/plans/2026-07-31-merge-lockstep.md`.
**Mode:** Inline Execution (roadmap track Q1).
