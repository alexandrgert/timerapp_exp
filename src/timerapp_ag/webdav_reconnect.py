"""Логика edge offline→online для отложенного WebDAV push."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class WebDavReconnectGate:
    """Решает, нужно ли запускать push после восстановления сети."""

    debounce_seconds: float = 2.5
    cooldown_seconds: float = 60.0
    was_offline: bool = False
    sync_in_progress: bool = False
    deferred_while_busy: bool = False
    last_push_monotonic: float = 0.0
    _pending_online_at: float | None = field(default=None, repr=False)

    def mark_offline(self) -> None:
        self.was_offline = True
        self._pending_online_at = None
        self.deferred_while_busy = False

    def on_online(self, *, busy: bool = False, now: float | None = None) -> bool:
        """True, если нужно стартовать debounce-таймер на push."""
        if not self.was_offline and not self.deferred_while_busy:
            return False
        if busy or self.sync_in_progress:
            # сеть уже есть, но sync занят — догоним после idle
            if self.was_offline:
                self.deferred_while_busy = True
            return False
        stamp = time.monotonic() if now is None else now
        if self.last_push_monotonic and (stamp - self.last_push_monotonic) < self.cooldown_seconds:
            self.deferred_while_busy = False
            return False
        self.deferred_while_busy = False
        self._pending_online_at = stamp
        # was_offline остаётся True до begin_push / успешного defer clear
        if not self.was_offline:
            self.was_offline = True
        return True

    def on_busy_finished(self, *, now: float | None = None) -> bool:
        """После окончания другого sync: True → стартовать debounce."""
        if not self.deferred_while_busy:
            return False
        return self.on_online(busy=False, now=now)

    def should_fire_push(self, *, now: float | None = None) -> bool:
        """True после debounce, если всё ещё актуален offline→online edge."""
        if not self.was_offline or self._pending_online_at is None:
            return False
        if self.sync_in_progress:
            return False
        stamp = time.monotonic() if now is None else now
        if stamp - self._pending_online_at < self.debounce_seconds:
            return False
        if self.last_push_monotonic and (stamp - self.last_push_monotonic) < self.cooldown_seconds:
            return False
        return True

    def begin_push(self, *, now: float | None = None) -> bool:
        """Занять слот push; False если уже занято / не готово."""
        if not self.should_fire_push(now=now):
            return False
        self.sync_in_progress = True
        self.was_offline = False
        self._pending_online_at = None
        self.deferred_while_busy = False
        return True

    def defer_fire_until_idle(self) -> None:
        """Debounce сработал, но sync занят — не теряем reconnect."""
        self.was_offline = True
        self._pending_online_at = None
        self.deferred_while_busy = True
        self.sync_in_progress = False

    def end_push(self, *, now: float | None = None) -> None:
        self.sync_in_progress = False
        self.last_push_monotonic = time.monotonic() if now is None else now

    # Совместимость со старыми вызовами
    def mark_online(self, *, now: float | None = None) -> bool:
        return self.on_online(busy=False, now=now)

    def note_other_sync_started(self) -> None:
        self.sync_in_progress = True

    def note_other_sync_finished(self) -> None:
        self.sync_in_progress = False
