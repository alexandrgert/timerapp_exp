from __future__ import annotations

import os
from datetime import datetime, timedelta

from .bitrix_config import BitrixPortalConfig, merge_portal_config
from .bitrix_secrets import import_webhook_from_ui, load_bitrix_webhook, save_bitrix_webhook
from .bitrix_transfer_journal import apply_transfer_journal, remove_transfer_result
from .domain import formatting
from .domain import plan as plan_domain
from .domain import priority as priority_domain
from .domain import queries
from .domain import reminders as reminders_domain
from .domain.sync_normalize import normalize_running_tasks
from .domain import task_ops
from .domain.constants import DEFAULT_REMINDER_INTERVAL_MINUTES, REMINDER_GRACE_MINUTES
from .domain.state import AppState
from .models import Session, Task, TaskStatus
from .storage import Storage
from .webdav_config import peek_webdav_pending_notice
from .webdav_sync import SyncOutcome, sync_webdav_on_startup


class AppController:
    reminder_grace = timedelta(minutes=REMINDER_GRACE_MINUTES)

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.pending_confirmation_task_id: str | None = None
        self.pending_confirmation_deadline: datetime | None = None
        self.next_reminder_at: datetime | None = None
        self.focus_paused_task_id: str | None = None
        self.focus_session_task_id: str | None = None
        self.focus_resume_offer_pending = False
        self.webdav_startup_notice: str | None = None
        self.state = storage.load()
        self._migrate_bitrix_webhook_from_data()
        if plan_domain.migrate_schema_v2(self.state, today=self.today_str()):
            self.save()
        self._apply_pending_bitrix_transfers()
        self._apply_env_bitrix_webhook()
        self.apply_loaded_state()
        self.state.ui.setdefault("reminder_interval_minutes", DEFAULT_REMINDER_INTERVAL_MINUTES)

    def run_deferred_startup_sync(self) -> bool:
        """Pull WebDAV after the UI is shown. Returns True if state changed."""
        outcome = sync_webdav_on_startup(self.storage)
        if outcome.state is not None:
            self.state = outcome.state
        if outcome.error:
            self.webdav_startup_notice = f"WebDAV: не удалось синхронизировать при запуске — {outcome.error}"
        elif outcome.notice:
            self.webdav_startup_notice = f"WebDAV: {outcome.notice}"
        pending = peek_webdav_pending_notice()
        if pending:
            pending_line = f"WebDAV: {pending}"
            if self.webdav_startup_notice:
                self.webdav_startup_notice = f"{self.webdav_startup_notice}\n{pending_line}"
            else:
                self.webdav_startup_notice = pending_line
        if outcome.state is not None:
            self.apply_loaded_state()
            return True
        return False

    def _apply_pending_bitrix_transfers(self) -> None:
        applied = apply_transfer_journal(self.storage, self.mark_sessions_transferred)
        if applied:
            self.state = self.storage.load()

    def reload_state_from_storage(self) -> None:
        self.state = self.storage.load()
        self.apply_loaded_state()

    def apply_loaded_state(self) -> None:
        """После load/pull: миграция секретов, rollover, одна running-задача, runtime таймера."""
        self._migrate_bitrix_webhook_from_data()
        changed_rollover = plan_domain.ensure_plan_rollover(self.state, today=self.today_str())
        changed_running = normalize_running_tasks(self.state)
        self.pending_confirmation_task_id = None
        self.pending_confirmation_deadline = None
        if changed_rollover or changed_running:
            self._clear_reminder_runtime()
            self.save()
        else:
            self._close_cross_day_side_effects()
        self._rebuild_runtime_state()
        self._sanitize_focus_timer_on_load()
        self._finalize_expired_focus_on_load()

    def _sanitize_focus_timer_on_load(self) -> None:
        """Close orphaned focus sessions when timer state and tasks disagree."""
        timer = reminders_domain.focus_timer(self.state)
        session_task_id = timer.get("session_task_id")
        ends_at = timer.get("ends_at")
        changed = False

        if session_task_id and not ends_at:
            self.focus_session_task_id = str(session_task_id)
            self._finish_focus_session()
            changed = True

        for task in self.state.tasks:
            if task.description.strip() != "Режим концентрации":
                continue
            if task.is_completed() or task.active_session() is None:
                continue
            if session_task_id == task.id and ends_at:
                continue
            task_ops.finish_focus_session_task(self.state, task.id)
            changed = True

        if changed:
            self.save()

    def _finalize_expired_focus_on_load(self) -> None:
        timer = reminders_domain.focus_timer(self.state)
        if not timer.get("ends_at"):
            return
        if reminders_domain.focus_remaining_seconds(self.state) > 0:
            return
        self.check_focus_timer()

    def save(self) -> None:
        self.storage.save(self.state)

    def today_str(self) -> str:
        return queries.today_str()

    def _clear_reminder_runtime(self) -> None:
        self.pending_confirmation_task_id = None
        self.pending_confirmation_deadline = None
        self.next_reminder_at = None

    def _close_cross_day_side_effects(self) -> None:
        if plan_domain.close_cross_day_active_task(self.state, self.today_str()):
            self._clear_reminder_runtime()
            self.save()

    def _rebuild_runtime_state(self) -> None:
        self.next_reminder_at = reminders_domain.rebuild_next_reminder_at(self.state)
        timer = reminders_domain.focus_timer(self.state)
        paused = timer.get("paused_task_id")
        self.focus_paused_task_id = str(paused) if paused else None
        session_task_id = timer.get("session_task_id")
        if session_task_id and timer.get("ends_at"):
            self.focus_session_task_id = str(session_task_id)
        else:
            self.focus_session_task_id = None

    def _set_focus_paused_task_id(self, task_id: str | None) -> None:
        self.focus_paused_task_id = task_id
        reminders_domain.focus_timer(self.state)["paused_task_id"] = task_id

    def _finish_focus_session(self, *, now: datetime | None = None) -> None:
        now = now or datetime.now()
        task_id = self.focus_session_task_id
        timer = reminders_domain.focus_timer(self.state)
        if task_id is None:
            stored = timer.get("session_task_id")
            task_id = str(stored) if stored else None
        if not task_id:
            self.focus_session_task_id = None
            timer["session_task_id"] = None
            return
        try:
            task_ops.finish_focus_session_task(self.state, task_id, now=now)
        except KeyError:
            pass
        self.focus_session_task_id = None
        timer["session_task_id"] = None

    def _migrate_bitrix_webhook_from_data(self) -> None:
        if not import_webhook_from_ui(self.state.ui):
            return
        self.save()

    def _apply_env_bitrix_webhook(self) -> None:
        if self.bitrix_webhook():
            return
        env_url = (os.environ.get("BITRIX24_HOOK_URL") or "").strip()
        if env_url:
            save_bitrix_webhook(env_url)

    def bitrix_webhook(self) -> str:
        return load_bitrix_webhook()

    def set_bitrix_webhook(self, url: str) -> None:
        save_bitrix_webhook((url or "").strip())
        if import_webhook_from_ui(self.state.ui):
            self.save()

    def bitrix_portal_config(self) -> BitrixPortalConfig:
        bitrix = self.state.ui.get("bitrix")
        stored = bitrix.get("portal") if isinstance(bitrix, dict) else None
        return merge_portal_config(stored)

    def set_bitrix_portal_config(self, config: BitrixPortalConfig) -> None:
        bitrix = self.state.ui.setdefault("bitrix", {})
        bitrix["portal"] = config.to_dict()
        self.save()

    def reminder_interval_minutes(self) -> int:
        return reminders_domain.reminder_interval_minutes(self.state)

    def set_reminder_interval_minutes(self, minutes: int) -> None:
        before = self.reminder_interval_minutes()
        value = reminders_domain.clamp_reminder_interval(minutes)
        self.state.ui["reminder_interval_minutes"] = value
        if value != before and not self.pending_confirmation_task_id:
            active = queries.active_task(self.state)
            if active and active.active_session():
                self.next_reminder_at = datetime.now() + reminders_domain.reminder_interval_td(self.state)
        self.save()

    def ensure_plan_rollover(self, today: str | None = None) -> None:
        if plan_domain.ensure_plan_rollover(self.state, today=today or self.today_str()):
            self._clear_reminder_runtime()
            self.save()
        else:
            self._close_cross_day_side_effects()

    def all_tasks(self) -> list[Task]:
        return queries.all_tasks(self.state)

    def tasks_all(self) -> list[Task]:
        return queries.tasks_all(self.state)

    def tasks_in_progress(self) -> list[Task]:
        return queries.tasks_in_progress(self.state)

    def tasks_today_plan(self, today: str | None = None) -> list[Task]:
        return queries.tasks_today_plan(
            self.state,
            today or self.today_str(),
            priority_levels=self.priority_filter_levels(),
        )

    def task_priority(self, task: Task, day: str | None = None) -> int:
        return priority_domain.task_priority(task, day or self.today_str())

    def set_tasks_priority(
        self,
        task_ids: list[str],
        priority: int,
        day: str | None = None,
    ) -> None:
        today = day or self.today_str()
        priority = priority_domain.clamp_priority(priority)
        if priority == priority_domain.DEFAULT_PRIORITY:
            changed = bool(
                priority_domain.clear_tasks_priority(self.state, task_ids, today)
            )
        else:
            changed = bool(
                priority_domain.set_tasks_priority(self.state, task_ids, today, priority)
            )
            for task_id in task_ids:
                if plan_domain.add_to_plan(self.state, task_id, today):
                    changed = True
        if changed:
            self.save()

    def assign_tasks_priority(
        self,
        task_ids: list[str],
        priority: int,
        day: str | None = None,
        *,
        add_to_plan: bool = False,
    ) -> None:
        today = day or self.today_str()
        priority = priority_domain.clamp_priority(priority)
        changed = bool(
            priority_domain.assign_tasks_priority(self.state, task_ids, today, priority)
        )
        if add_to_plan or priority != priority_domain.DEFAULT_PRIORITY:
            for task_id in task_ids:
                if plan_domain.add_to_plan(self.state, task_id, today):
                    changed = True
        if changed:
            self.save()

    def priority_filter_levels(self) -> set[int]:
        return priority_domain.priority_filter_levels(self.state.ui)

    def set_priority_filter_levels(self, levels: set[int]) -> None:
        if priority_domain.set_priority_filter_levels(self.state.ui, levels):
            self.save()

    def tasks_on_date(self, date_iso: str) -> list[Task]:
        return queries.tasks_on_date(self.state, date_iso)

    def in_today_plan(self, task: Task, today: str | None = None) -> bool:
        return queries.in_today_plan(task, today or self.today_str())

    def visible_on_today_plan(self, task: Task, today: str | None = None) -> bool:
        return queries.visible_on_today_plan(task, today or self.today_str())

    def add_to_plan(self, task_id: str, today: str | None = None) -> None:
        if plan_domain.add_to_plan(self.state, task_id, today or self.today_str()):
            self.save()

    def add_to_plan_with_priority(
        self,
        task_id: str,
        priority: int,
        today: str | None = None,
    ) -> None:
        day = today or self.today_str()
        changed = plan_domain.add_to_plan(self.state, task_id, day)
        if priority_domain.assign_task_priority_for_day(self.state, task_id, day, priority):
            changed = True
        if changed:
            self.save()

    def remove_from_plan(self, task_id: str, today: str | None = None) -> None:
        if plan_domain.remove_from_plan(self.state, task_id, today or self.today_str()):
            self.save()

    def today_seconds(self, task: Task, today: str | None = None) -> int:
        return queries.today_seconds(task, today or self.today_str())

    def today_total_seconds(self, today: str | None = None) -> int:
        return queries.today_total_seconds(self.state, today or self.today_str())

    def tasks_by_day(self, open_only: bool = False) -> list[tuple[str, list[Task]]]:
        return queries.tasks_by_day(self.state, open_only=open_only)

    def day_total_seconds(self, day: str) -> int:
        return queries.day_total_seconds(self.state, day)

    def find_task(self, task_id: str) -> Task:
        return queries.find_task(self.state, task_id)

    def create_task(
        self,
        title: str,
        description: str = "",
        start_now: bool = False,
        bitrix: dict | None = None,
    ) -> Task:
        task = task_ops.create_task(self.state, title, description=description, bitrix=bitrix)
        self.save()
        if start_now:
            self.start_task(task.id)
        return task

    def link_bitrix(self, task_id: str, link: dict) -> None:
        task_ops.link_bitrix(self.state, task_id, link)
        self.save()

    def import_bitrix_items(self, items: list[dict]) -> tuple[int, int]:
        imported, skipped = task_ops.import_bitrix_items(self.state, items, day=self.today_str())
        if imported:
            self.save()
        return imported, skipped

    def running_tasks(self) -> list[Task]:
        return queries.running_tasks(self.state)

    def active_task(self) -> Task | None:
        return queries.active_task(self.state)

    def timer_panel_task(self) -> Task | None:
        return queries.timer_panel_task(self.state)

    def start_task(self, task_id: str) -> Task:
        self.stop_focus_timer()
        self._set_focus_paused_task_id(None)
        self.focus_resume_offer_pending = False
        plan_domain.add_to_plan(self.state, task_id, self.today_str())
        now = datetime.now()
        task = task_ops.start_task(self.state, task_id, now=now)
        self._clear_reminder_runtime()
        self.next_reminder_at = now + reminders_domain.reminder_interval_td(self.state)
        self.save()
        return task

    def stop_task(self, task_id: str, now: datetime | None = None) -> Task:
        task = task_ops.stop_task(self.state, task_id, now=now)
        if self.pending_confirmation_task_id == task_id:
            self.pending_confirmation_task_id = None
            self.pending_confirmation_deadline = None
        if queries.active_task(self.state) is None:
            self.next_reminder_at = None
        self.save()
        return task

    def complete_task(self, task_id: str) -> Task:
        task = task_ops.complete_task(self.state, task_id)
        self._clear_reminder_runtime()
        self.save()
        return task

    def resume_completed_task(self, task_id: str) -> Task:
        task = task_ops.resume_completed_task(self.state, task_id)
        self._clear_reminder_runtime()
        self.next_reminder_at = datetime.now() + reminders_domain.reminder_interval_td(self.state)
        self.save()
        return task

    def delete_task(self, task_id: str) -> None:
        timer = reminders_domain.focus_timer(self.state)
        if task_id == self.focus_session_task_id or timer.get("session_task_id") == task_id:
            self._finish_focus_session()
            timer["ends_at"] = None
            timer["duration_minutes"] = None
        if task_id == self.focus_paused_task_id:
            self._set_focus_paused_task_id(None)
            self.focus_resume_offer_pending = False
        task_ops.delete_task(self.state, task_id)
        if self.pending_confirmation_task_id == task_id:
            self._clear_reminder_runtime()
        if queries.active_task(self.state) is None:
            self.next_reminder_at = None
        self.save()

    def set_filter_open_only(self, value: bool) -> None:
        self.state.ui["filter_open_only"] = value
        self.save()

    def filter_open_only(self) -> bool:
        return bool(self.state.ui.get("filter_open_only", False))

    def focus_timer_state(self) -> dict[str, object]:
        return dict(reminders_domain.focus_timer(self.state))

    def start_focus_timer(self, minutes: int) -> None:
        now = datetime.now()
        active = self.active_task()
        panel_task = self.timer_panel_task()
        pause_task = active
        if pause_task is None and panel_task is not None and not panel_task.is_completed():
            pause_task = panel_task

        self._set_focus_paused_task_id(None)
        if pause_task is not None:
            if pause_task.status == TaskStatus.RUNNING:
                task_ops.stop_task(self.state, pause_task.id, now=now)
                self.next_reminder_at = None
            self._set_focus_paused_task_id(pause_task.id)

        self._finish_focus_session(now=now)

        focus_task = task_ops.create_focus_session_task(self.state, minutes, now=now)
        self.focus_session_task_id = focus_task.id

        timer = reminders_domain.focus_timer(self.state)
        timer["selected_minutes"] = minutes
        timer["duration_minutes"] = minutes
        timer["ends_at"] = (now + timedelta(minutes=minutes)).isoformat()
        timer["session_task_id"] = focus_task.id
        self.focus_resume_offer_pending = False
        self.save()

    def stop_focus_timer(self) -> None:
        self._finish_focus_session()
        timer = reminders_domain.focus_timer(self.state)
        timer["ends_at"] = None
        timer["duration_minutes"] = None
        self.save()

    def take_focus_paused_task_id(self) -> str | None:
        task_id = self.focus_paused_task_id
        self._set_focus_paused_task_id(None)
        self.focus_resume_offer_pending = False
        if task_id is not None:
            self.save()
        return task_id

    def focus_remaining_seconds(self) -> int:
        return reminders_domain.focus_remaining_seconds(self.state)

    def check_focus_timer(self) -> tuple[str, int | None]:
        timer = reminders_domain.focus_timer(self.state)
        planned_end = timer.get("ends_at")
        status, minutes = reminders_domain.check_focus_timer(self.state)
        if status == "finished":
            end = (
                datetime.fromisoformat(str(planned_end))
                if planned_end
                else datetime.now()
            )
            self._finish_focus_session(now=end)
            if self.focus_paused_task_id:
                self.focus_resume_offer_pending = True
            self.save()
        return status, minutes

    def check_reminders(self) -> tuple[str, Task | None]:
        self.ensure_plan_rollover()
        (
            status,
            active,
            pending_id,
            pending_deadline,
            next_at,
            needs_save,
        ) = reminders_domain.check_reminders(
            self.state,
            pending_confirmation_task_id=self.pending_confirmation_task_id,
            pending_confirmation_deadline=self.pending_confirmation_deadline,
            next_reminder_at=self.next_reminder_at,
        )
        self.pending_confirmation_task_id = pending_id
        self.pending_confirmation_deadline = pending_deadline
        self.next_reminder_at = next_at
        if needs_save:
            self.save()
        return status, active

    def confirm_continue(self, task_id: str) -> None:
        task = self.find_task(task_id)
        if task.status != TaskStatus.RUNNING:
            return
        self.pending_confirmation_task_id = None
        self.pending_confirmation_deadline = None
        self.next_reminder_at = datetime.now() + reminders_domain.reminder_interval_td(self.state)
        self.save()

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> Task:
        task = task_ops.update_task(
            self.state,
            task_id,
            title=title,
            description=description,
        )
        self.save()
        return task

    def add_session(
        self,
        task_id: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        comment: str = "",
    ) -> Session:
        session = task_ops.add_session(
            self.state,
            task_id,
            started_at,
            ended_at,
            comment=comment,
        )
        self.save()
        return session

    def delete_session(self, task_id: str, session_id: str) -> None:
        removed_running = task_ops.delete_session(self.state, task_id, session_id)
        if self.pending_confirmation_task_id == task_id:
            if queries.find_task(self.state, task_id).active_session() is None:
                self.pending_confirmation_task_id = None
                self.pending_confirmation_deadline = None
        if removed_running and queries.active_task(self.state) is None:
            self.next_reminder_at = None
        self.save()

    def update_session(
        self,
        task_id: str,
        session_id: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        comment: str | None = None,
    ) -> None:
        task_ops.update_session(
            self.state,
            task_id,
            session_id,
            started_at,
            ended_at,
            comment=comment,
        )
        self.save()

    def mark_sessions_transferred(self, task_id: str, session_ids, record_id) -> None:
        """Mark given sessions as transferred to Bitrix with the created record id."""
        ids = set(session_ids)
        for session in self.find_task(task_id).sessions:
            if session.id in ids:
                session.bitrix_record_id = str(record_id)
        self.save()

    def finalize_sessions_transfer(self, task_id: str, session_ids, record_id) -> None:
        """Remove a durable journal entry after the UI applied a transfer."""
        remove_transfer_result(self.storage, task_id, list(session_ids), str(record_id))

    def task_elapsed_text(self, task: Task) -> str:
        return formatting.format_duration(task.total_seconds(datetime.now()))


# Backward-compatible re-exports for UI and tests
format_duration = formatting.format_duration
format_hm = formatting.format_hm
format_day_label = formatting.format_day_label
