"""TaskTimer causal WebDAV v2. Wire contract: docs/sync-v2.md."""
from __future__ import annotations
import copy
import json
import math
import re

MAX_OPS = 20000
MAX_BYTES = 20 * 1024 * 1024


def empty_document():
    return {"format": "tasktimer-sync", "version": 2, "ops": []}


def _json(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        value.encode("utf-8", "strict")
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or abs(value) > 1.7976931348623157e308:
            raise ValueError("Некорректное число JSON")
        return float(value)
    if isinstance(value, list):
        return [_json(x) for x in value]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {_json(k): _json(v) for k, v in value.items()}
    raise ValueError("Ожидались JSON данные")


def equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (float, int)) and isinstance(b, (float, int)):
        return float(a) == float(b)
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def _key(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _dot(op):
    return _key([op["actor"], op["seq"]])


def _actor(a):
    return isinstance(a, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", a)) and a not in {"__proto__", "constructor", "prototype"}


def _entity(e):
    return isinstance(e, list) and ((len(e) == 2 and e[0] == "task") or (len(e) == 3 and e[0] == "session")) and all(isinstance(x, str) and 0 < len(x) <= 512 for x in e[1:])


def _integer(n):
    return type(n) is int and 1 <= n <= 9007199254740991


def validate_document(doc):
    if not isinstance(doc, dict) or doc.get("format") != "tasktimer-sync" or type(doc.get("version")) is not int or doc["version"] != 2 or not isinstance(doc.get("ops"), list):
        raise ValueError("Неподдерживаемый формат синхронизации")
    _json(doc)
    if len(doc["ops"]) > MAX_OPS or len(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_BYTES:
        raise ValueError("Журнал синхронизации превышает безопасный размер; данные не изменены")
    dots = {}
    counts = {}
    for op in doc["ops"]:
        if not isinstance(op, dict) or not _actor(op.get("actor")) or not _integer(op.get("seq")) or not isinstance(op.get("seen"), dict) or not _entity(op.get("entity")) or not isinstance(op.get("changes"), dict) or not op["changes"]:
            raise ValueError("Некорректная операция синхронизации")
        if any(not _actor(a) or not _integer(n) for a, n in op["seen"].items()) or op["seen"].get(op["actor"], 0) != op["seq"] - 1:
            raise ValueError("Некорректный причинный контекст")
        changes = op["changes"]
        if "$alive" in changes and type(changes["$alive"]) is not bool:
            raise ValueError("Некорректная отметка существования")
        if any(k in {"id", "sessions", "__proto__", "constructor", "prototype"} for k in changes):
            raise ValueError("Зарезервированное поле")
        if op["entity"][0] == "session" and "interval" in changes and (not isinstance(changes["interval"], dict) or not set(changes["interval"]) <= {"started_at", "ended_at", "duration_seconds"}):
            raise ValueError("Некорректный интервал сессии")
        d = _dot(op)
        if d in dots:
            raise ValueError("Повтор операции")
        dots[d] = op
        counts.setdefault(op["actor"], set()).add(op["seq"])
    if any(len(s) != max(s) for s in counts.values()):
        raise ValueError("Неполный журнал устройства")
    for op in doc["ops"]:
        for a, n in op["seen"].items():
            prev = dots.get(_key([a, n]))
            if prev is None or prev["seen"].get(op["actor"], 0) >= op["seq"] or any(op["seen"].get(b, 0) < m for b, m in prev["seen"].items()):
                raise ValueError("Некорректный причинный предшественник")
    return copy.deepcopy(doc)


def merge_documents(a, b):
    a, b = validate_document(a), validate_document(b)
    ops = {_dot(o): o for o in a["ops"]}
    for op in b["ops"]:
        d = _dot(op)
        if d in ops and not equal(ops[d], op):
            raise ValueError("Коллизия идентификатора устройства")
        ops[d] = op
    for k, v in b.items():
        if k != "ops":
            if k in a and not equal(a[k], v):
                raise ValueError("Конфликт расширения формата")
            a[k] = v
    a["ops"] = [ops[k] for k in sorted(ops)]
    return validate_document(a)


def _append(doc, actor, entity, changes, *, ordinary=True):
    if not _actor(actor) or not _entity(entity):
        raise ValueError("Некорректная правка")
    seen = {}
    for o in doc["ops"]:
        seen[o["actor"]] = max(seen.get(o["actor"], 0), o["seq"])
    values = {"$alive": True, **copy.deepcopy(changes)} if ordinary else copy.deepcopy(changes)
    doc["ops"].append({"actor": actor, "seq": seen.get(actor, 0) + 1, "seen": seen, "entity": entity[:], "changes": values})
    if ordinary and entity[0] == "session":
        _append(doc, actor, ["task", entity[1]], {"$alive": True})


def change_entity(doc, actor, entity, changes):
    doc = validate_document(doc)
    _append(doc, actor, entity, changes)
    return validate_document(doc)


def project_document(doc):
    doc = validate_document(doc)
    groups = {}
    for op in doc["ops"]:
        groups.setdefault(_key(op["entity"]), []).append(op)
    entities, conflicts = [], []
    for entity_key, ops in sorted(groups.items()):
        entity, values = json.loads(entity_key), {}
        for field in sorted({f for o in ops for f in o["changes"]}):
            writes = [o for o in ops if field in o["changes"]]
            observed = {}
            for p in writes:
                for a, n in p["seen"].items():
                    observed[a] = max(observed.get(a, 0), n)
            maximal = [o for o in writes if observed.get(o["actor"], 0) < o["seq"]]
            candidates = []
            for op in maximal:
                candidate = next((c for c in candidates if equal(c["value"], op["changes"][field])), None)
                if candidate is None:
                    candidate = {"value": copy.deepcopy(op["changes"][field]), "dots": []}
                    candidates.append(candidate)
                candidate["dots"].append([op["actor"], op["seq"]])
            for c in candidates:
                c["dots"].sort(key=_key)
            candidates.sort(key=lambda c: _key(c["dots"][0]))
            if len(candidates) > 1:
                conflicts.append({"entity": entity, "field": field, "candidates": candidates})
            values[field] = candidates[0]["value"]
            if field == "$alive" and any(c["value"] is False for c in candidates):
                values[field] = False
        entities.append({"entity": entity, "deleted": values.get("$alive") is False, "values": values})
    return {"entities": entities, "conflicts": conflicts}


def resolve_conflict(doc, actor, entity, field, value):
    conflict = next((c for c in project_document(doc)["conflicts"] if c["entity"] == entity and c["field"] == field), None)
    if not conflict or not any(equal(c["value"], value) for c in conflict["candidates"]):
        raise ValueError("Конфликт изменился; обновите список")
    doc = validate_document(doc)
    _append(doc, actor, entity, {field: value}, ordinary=False)
    return validate_document(doc)


def _flatten(tasks):
    result = {}
    if not isinstance(tasks, list):
        raise ValueError("Ожидался список задач")
    for task in tasks:
        entity = ["task", task.get("id")]
        if not _entity(entity) or _key(entity) in result or not isinstance(task.get("sessions"), list):
            raise ValueError("Некорректная задача")
        values = copy.deepcopy(task)
        del values["id"]
        del values["sessions"]
        result[_key(entity)] = values
        for session in task["sessions"]:
            se = ["session", task["id"], session.get("id")]
            if not _entity(se) or _key(se) in result:
                raise ValueError("Некорректная сессия")
            sv = copy.deepcopy(session)
            del sv["id"]
            sv["interval"] = {f: sv.pop(f) for f in ("started_at", "ended_at", "duration_seconds") if f in sv}
            result[_key(se)] = sv
    return result


def reconcile_tasks(doc, before, after, actor):
    doc = validate_document(doc)
    before, after = _flatten(before), _flatten(after)
    for k in sorted(before.keys() | after.keys(), key=lambda k: (0 if json.loads(k)[0] == "task" else 1, k)):
        old, new, entity = before.get(k), after.get(k), json.loads(k)
        if new is None:
            if entity[0] == "session" and _key(["task", entity[1]]) not in after:
                continue
            _append(doc, actor, entity, {"$alive": False})
        else:
            changes = {f: v for f, v in new.items() if old is None or f not in old or not equal(old[f], v)}
            if changes:
                _append(doc, actor, entity, changes)
    return validate_document(doc)


def import_legacy(tasks, actor):
    return reconcile_tasks(empty_document(), [], tasks, actor)


def project_tasks(doc):
    result = project_document(doc)
    tasks = []
    for e in result["entities"]:
        if e["entity"][0] != "task" or e["deleted"] or "title" not in e["values"]:
            continue
        task = copy.deepcopy(e["values"])
        task.pop("$alive", None)
        task.update(id=e["entity"][1], sessions=[])
        for s in result["entities"]:
            if s["entity"][0] != "session" or s["entity"][1] != task["id"] or s["deleted"]:
                continue
            session = copy.deepcopy(s["values"])
            session.pop("$alive", None)
            interval = session.pop("interval", {})
            session.update(interval)
            session["id"] = s["entity"][2]
            task["sessions"].append(session)
        tasks.append(task)
    return {"tasks": tasks, "conflicts": result["conflicts"]}
