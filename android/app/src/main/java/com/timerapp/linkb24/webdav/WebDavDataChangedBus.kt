package com.timerapp.linkb24.webdav

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/** Сигнал «data.json на диске изменился вне TaskViewModel» (reconnect merge и т.п.). */
object WebDavDataChangedBus {
    private val _events = MutableSharedFlow<Unit>(
        extraBufferCapacity = 1,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val events: SharedFlow<Unit> = _events.asSharedFlow()

    fun notifyDataChanged() {
        _events.tryEmit(Unit)
    }
}
