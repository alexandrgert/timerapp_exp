package com.timerapp.linkb24.sync

import kotlinx.serialization.json.*

/** Language-neutral causal log. Unknown JSON fields remain in the authoritative log. */
object SyncV2 {
    const val MAX_BYTES = 20 * 1024 * 1024
    private const val MAX_SEQ = 9007199254740991L
    private val forbidden = setOf("__proto__", "constructor", "prototype")
    private val scalarOrder = Comparator<String> { a, b ->
        val x = a.codePoints().toArray(); val y = b.codePoints().toArray()
        var result = 0
        for (i in 0 until minOf(x.size, y.size)) { if (x[i] != y[i]) { result = x[i].compareTo(y[i]); break } }
        if (result == 0) x.size.compareTo(y.size) else result
    }
    fun decodeUtf8(bytes: ByteArray): String = try {
        Charsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString()
    } catch (error: java.nio.charset.CharacterCodingException) { throw IllegalArgumentException("Некорректный UTF-8 в данных синхронизации", error) }
    fun empty(): JsonObject = buildJsonObject { put("format", "tasktimer-sync"); put("version", 2); put("ops", JsonArray(emptyList())) }
    private fun actorValid(value: String) = Regex("[A-Za-z0-9_.:-]{1,160}").matches(value) && value !in forbidden
    private fun string(value: JsonElement?): String = (value as? JsonPrimitive)?.takeIf { it.isString }?.content ?: error("Ожидалась строка синхронизации")
    private fun integer(value: JsonElement?): Long {
        val p = value as? JsonPrimitive ?: error("Некорректная версия")
        require(!p.isString && p.booleanOrNull == null)
        val d = p.doubleOrNull ?: error("Некорректная версия")
        require(d.isFinite() && d >= 1 && d <= MAX_SEQ && d == d.toLong().toDouble())
        return d.toLong()
    }
    private fun entity(value: JsonElement?): JsonArray {
        val e = value as? JsonArray ?: error("Некорректная запись")
        require((e.size == 2 && string(e[0]) == "task") || (e.size == 3 && string(e[0]) == "session"))
        e.drop(1).forEach { require(string(it).length in 1..512) }
        return e
    }
    private fun unicode(value: String) {
        var i = 0
        while (i < value.length) {
            val c = value[i++]
            if (c.isHighSurrogate()) { require(i < value.length && value[i].isLowSurrogate()) { "Некорректный Unicode" }; i++ }
            else require(!c.isLowSurrogate()) { "Некорректный Unicode" }
        }
    }
    fun canonical(value: JsonElement): String = when (value) {
        is JsonObject -> value.keys.sortedWith(scalarOrder).joinToString(",", "{", "}") { unicode(it); JsonPrimitive(it).toString() + ":" + canonical(value.getValue(it)) }
        is JsonArray -> value.joinToString(",", "[", "]") { canonical(it) }
        is JsonPrimitive -> { if (value.isString) unicode(value.content) else if (value != JsonNull && value.booleanOrNull == null) require(value.double.isFinite()); value.toString() }
    }
    fun equal(a: JsonElement, b: JsonElement): Boolean = when {
        a is JsonObject && b is JsonObject -> a.keys == b.keys && a.all { (k,v) -> equal(v,b.getValue(k)) }
        a is JsonArray && b is JsonArray -> a.size == b.size && a.indices.all { equal(a[it], b[it]) }
        a is JsonPrimitive && b is JsonPrimitive -> when {
            a == JsonNull || b == JsonNull -> a == b
            a.isString || b.isString -> a.isString == b.isString && a.content == b.content
            a.booleanOrNull != null || b.booleanOrNull != null -> a.booleanOrNull == b.booleanOrNull
            else -> a.double == b.double
        }
        else -> false
    }
    private fun ops(doc: JsonObject) = doc.getValue("ops").jsonArray.map { it.jsonObject }
    private fun dot(op: JsonObject) = JsonArray(listOf(op.getValue("actor"), JsonPrimitive(integer(op["seq"])))).toString()
    private fun context(op: JsonObject) = op.getValue("seen").jsonObject.mapValues { integer(it.value) }
    fun validate(doc: JsonObject): JsonObject {
        require(doc["format"] == JsonPrimitive("tasktimer-sync") && doc["version"]?.let { equal(it, JsonPrimitive(2)) } == true && doc["ops"] is JsonArray) { "Неподдерживаемый формат синхронизации" }
        require(doc.getValue("ops").jsonArray.size <= 20000 && canonical(doc).toByteArray(Charsets.UTF_8).size <= MAX_BYTES) { "Журнал синхронизации превышает безопасный размер" }
        val byDot = linkedMapOf<String, JsonObject>(); val counts = linkedMapOf<String, MutableSet<Long>>()
        for (op in ops(doc)) {
            val actor = string(op["actor"]); require(actorValid(actor)); val seq = integer(op["seq"])
            val seen = context(op); seen.keys.forEach { require(actorValid(it)) }
            require((seen[actor] ?: 0) == seq - 1) { "Разрыв последовательности устройства" }
            val e = entity(op["entity"]); val changes = op["changes"] as? JsonObject ?: error("Некорректная правка")
            require(changes.isNotEmpty() && changes.keys.none { it in forbidden || it == "id" || it == "sessions" })
            changes["\$alive"]?.let { require(it is JsonPrimitive && !it.isString && it.booleanOrNull != null) }
            if (e[0] == JsonPrimitive("session")) changes["interval"]?.let { interval -> require(interval is JsonObject && interval.keys.all { it in setOf("started_at", "ended_at", "duration_seconds") }) }
            require(byDot.put(dot(op), op) == null) { "Повтор идентификатора операции" }
            counts.getOrPut(actor) { mutableSetOf() }.add(seq)
        }
        counts.values.forEach { require(it.size.toLong() == it.maxOrNull()) { "Неполный журнал устройства" } }
        for (op in ops(doc)) for ((a,n) in context(op)) {
            val previous = byDot[JsonArray(listOf(JsonPrimitive(a),JsonPrimitive(n))).toString()] ?: error("Отсутствует причинный предшественник")
            val prior = context(previous); require((prior[string(op["actor"])] ?: 0) < integer(op["seq"])) { "Цикл причинных версий" }
            prior.forEach { (b,m) -> require((context(op)[b] ?: 0) >= m) { "Неполный причинный контекст" } }
        }
        return doc
    }
    fun merge(a: JsonObject, b: JsonObject): JsonObject {
        validate(a); validate(b); val combined = a.toMutableMap(); val rows = ops(a).associateBy(::dot).toMutableMap()
        for (op in ops(b)) { rows[dot(op)]?.let { require(equal(it, op)) { "Коллизия идентификатора устройства" } }; rows[dot(op)] = op }
        b.filterKeys { it != "ops" }.forEach { (k,v) -> combined[k]?.let { require(equal(it,v)) { "Конфликт расширения формата" } }; combined[k] = v }
        combined["ops"] = JsonArray(rows.toSortedMap().values.toList()); return validate(JsonObject(combined))
    }
    private fun append(doc: JsonObject, actor: String, e: JsonArray, changes: JsonObject, touch: Boolean): JsonObject {
        require(actorValid(actor)); val seen = mutableMapOf<String,Long>()
        ops(doc).forEach { op -> val a=string(op["actor"]); seen[a]=maxOf(seen[a] ?: 0, integer(op["seq"])) }
        val op=buildJsonObject { put("actor",actor); put("seq",(seen[actor] ?: 0)+1); put("seen",JsonObject(seen.mapValues { JsonPrimitive(it.value) })); put("entity",e); put("changes",changes) }
        var result=JsonObject(doc + ("ops" to JsonArray(ops(doc)+op)))
        if(touch && e[0]==JsonPrimitive("session")) result=append(result,actor,JsonArray(listOf(JsonPrimitive("task"),e[1])),buildJsonObject { put("\$alive",true) },false)
        return result
    }
    fun change(doc: JsonObject, actor: String, e: JsonArray, changes: JsonObject): JsonObject = validate(append(validate(doc),actor,entity(e),JsonObject(mapOf("\$alive" to JsonPrimitive(true))+changes),true))
    data class Candidate(val value: JsonElement, val dots: List<JsonArray>)
    data class Conflict(val entity: JsonArray, val field: String, val candidates: List<Candidate>)
    data class Entity(val entity: JsonArray, val deleted: Boolean, val values: JsonObject)
    data class Projection(val entities: List<Entity>, val conflicts: List<Conflict>)
    fun project(doc: JsonObject): Projection {
        validate(doc); val entities=mutableListOf<Entity>(); val conflicts=mutableListOf<Conflict>()
        val groups=ops(doc).groupBy { canonical(it.getValue("entity")) }
        for(k in groups.keys.sortedWith(scalarOrder)) {
            val rows=groups.getValue(k); val e=rows.first().getValue("entity").jsonArray; val values=linkedMapOf<String,JsonElement>()
            for(field in rows.flatMap { it.getValue("changes").jsonObject.keys }.toSet().sortedWith(scalarOrder)) {
                val writes=rows.filter { field in it.getValue("changes").jsonObject }; val seen=mutableMapOf<String,Long>()
                writes.forEach { context(it).forEach { (a,n)->seen[a]=maxOf(seen[a] ?: 0,n) } }
                val variants=mutableListOf<Pair<JsonElement,MutableList<JsonArray>>>()
                for(op in writes.filter { (seen[string(it["actor"])] ?: 0)<integer(it["seq"]) }) {
                    val value=op.getValue("changes").jsonObject.getValue(field)
                    val dots=variants.firstOrNull { equal(it.first,value) }?.second ?: mutableListOf<JsonArray>().also { variants.add(value to it) }
                    dots.add(JsonArray(listOf(op.getValue("actor"),JsonPrimitive(integer(op["seq"])))))
                }
                val candidates=variants.map { Candidate(it.first,it.second.sortedBy { d->d.toString() }) }.sortedBy { it.dots.first().toString() }
                require(candidates.isNotEmpty()); if(candidates.size>1)conflicts.add(Conflict(e,field,candidates))
                values[field]=if(field=="\$alive" && candidates.any { it.value==JsonPrimitive(false) }) JsonPrimitive(false) else candidates.first().value
            }
            entities.add(Entity(e,values["\$alive"]==JsonPrimitive(false),JsonObject(values)))
        }
        return Projection(entities,conflicts)
    }
    fun resolve(doc: JsonObject, actor: String, e: JsonArray, field: String, value: JsonElement): JsonObject {
        val conflict=project(doc).conflicts.firstOrNull { it.entity==e && it.field==field } ?: error("Конфликт уже изменился; обновите список")
        require(conflict.candidates.any { equal(it.value,value) }) { "Выберите сохранённый вариант" }
        return validate(append(doc,actor,e,JsonObject(mapOf(field to value)),false))
    }
    private fun flatten(tasks: JsonArray): Map<String,JsonObject> {
        val result=linkedMapOf<String,JsonObject>()
        for(item in tasks) {
            val task=item.jsonObject; val e=entity(JsonArray(listOf(JsonPrimitive("task"),task.getValue("id"))))
            require(result.put(canonical(e),JsonObject(task.filterKeys { it !in setOf("id","sessions") }))==null)
            for(itemSession in task.getValue("sessions").jsonArray) {
                val session=itemSession.jsonObject; val se=entity(JsonArray(listOf(JsonPrimitive("session"),e[1],session.getValue("id"))))
                val fields=session.filterKeys { it !in setOf("id","started_at","ended_at","duration_seconds") }.toMutableMap()
                fields["interval"]=JsonObject(session.filterKeys { it in setOf("started_at","ended_at","duration_seconds") })
                require(result.put(canonical(se),JsonObject(fields))==null)
            }
        }
        return result
    }
    fun reconcile(doc: JsonObject, before: JsonArray, after: JsonArray, actor: String): JsonObject {
        val old=flatten(before); val next=flatten(after); var result=validate(doc)
        val keys=(old.keys+next.keys).sortedWith(compareBy<String> { if(Json.parseToJsonElement(it).jsonArray[0]==JsonPrimitive("task")) 0 else 1 }.thenBy { it })
        for(k in keys) {
            val e=Json.parseToJsonElement(k).jsonArray; val a=old[k]; val b=next[k]
            if(b==null) {
                if(e[0]==JsonPrimitive("session") && canonical(JsonArray(listOf(JsonPrimitive("task"),e[1]))) !in next)continue
                result=append(result,actor,e,buildJsonObject { put("\$alive",false) },true);continue
            }
            val changed=b.filter { (f,v)->a?.get(f)?.let { !equal(it,v) } ?: true }
            if(changed.isNotEmpty())result=append(result,actor,e,JsonObject(mapOf("\$alive" to JsonPrimitive(true))+changed),true)
        }
        return validate(result)
    }
    fun importLegacy(tasks: JsonArray, actor: String)=reconcile(empty(),JsonArray(emptyList()),tasks,actor)
    fun tasks(doc: JsonObject): JsonArray {
        val projection=project(doc); val result=mutableListOf<JsonObject>()
        for(e in projection.entities.filter { it.entity[0]==JsonPrimitive("task") && !it.deleted && "title" in it.values }) {
            val sessions=projection.entities.filter { it.entity[0]==JsonPrimitive("session") && it.entity[1]==e.entity[1] && !it.deleted }.map { s ->
                JsonObject(s.values.filterKeys { it !in setOf("\$alive","interval") } + (s.values["interval"] as? JsonObject ?: JsonObject(emptyMap())) + ("id" to s.entity[2]))
            }
            result.add(JsonObject(e.values.filterKeys { it!="\$alive" }+mapOf("id" to e.entity[1],"sessions" to JsonArray(sessions))))
        }
        return JsonArray(result)
    }
}
