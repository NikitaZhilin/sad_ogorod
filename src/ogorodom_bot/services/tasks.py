from __future__ import annotations

import sqlite3
from datetime import timedelta

from ogorodom_bot.repositories.tasks import JournalRepository, ReminderRepository, TaskRepository
from ogorodom_bot.repositories.users import UserRepository
from ogorodom_bot.services.time_utils import (
    add_repeat,
    iso,
    local_day_bounds,
    parse_iso,
    quiet_adjusted,
    snooze_target,
    utc_now,
)


VALID_REPEAT_RULES = {"none", "daily", "weekly", "monthly", "yearly"}


class TaskService:
    def __init__(self, conn: sqlite3.Connection):
        self.tasks = TaskRepository(conn)
        self.journal = JournalRepository(conn)
        self.reminders = ReminderRepository(conn)
        self.users = UserRepository(conn)

    def create_task(
        self,
        user_id: int,
        title: str,
        due_at: str | None = None,
        description: str | None = None,
        repeat_rule: str = "none",
        remind_at: str | None = None,
        plot_id: int | None = None,
        zone_id: int | None = None,
        planting_id: int | None = None,
        work_type: str | None = None,
        wait_until_date: str | None = None,
    ) -> int:
        if not title.strip():
            raise ValueError("task title is required")
        if repeat_rule not in VALID_REPEAT_RULES:
            raise ValueError("repeat_rule must be none, daily, weekly, monthly or yearly")
        task_id = self.tasks.create(
            user_id=user_id,
            title=title.strip(),
            description=description,
            due_at=due_at,
            repeat_rule=repeat_rule,
            remind_at=remind_at,
            plot_id=plot_id,
            zone_id=zone_id,
            planting_id=planting_id,
            work_type=work_type,
            wait_until_date=wait_until_date,
        )
        self.journal.create(user_id, "task_created", f"Создана задача: {title}", "task", task_id)
        return task_id

    def list_open(self, user_id: int) -> list[dict]:
        return self.tasks.list_open(user_id)

    def get_task(self, user_id: int, task_id: int) -> dict | None:
        return self.tasks.get(task_id, user_id)

    def update_title(self, user_id: int, task_id: int, title: str) -> None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        title = title.strip()
        if not title:
            raise ValueError("task title is required")
        self.tasks.update_task(task_id, user_id, title=title)
        self.journal.create(user_id, "task_updated", f"Изменено название задачи: {title}", "task", task_id)

    def update_due_at(self, user_id: int, task_id: int, due_at: str | None) -> None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        remind_at = self.default_remind_at(user_id, due_at) if due_at else None
        self.tasks.update_task(
            task_id,
            user_id,
            due_at=due_at,
            remind_at=remind_at,
            clear_due=due_at is None,
        )
        note_due = due_at or "без срока"
        self.journal.create(user_id, "task_updated", f"Изменен срок задачи: {task['title']} -> {note_due}", "task", task_id)

    def update_repeat_rule(self, user_id: int, task_id: int, repeat_rule: str) -> None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        if repeat_rule not in VALID_REPEAT_RULES:
            raise ValueError("repeat_rule must be none, daily, weekly, monthly or yearly")
        self.tasks.update_task(task_id, user_id, repeat_rule=repeat_rule)
        self.journal.create(user_id, "task_updated", f"Изменен повтор задачи: {task['title']}", "task", task_id)

    def complete_task(self, user_id: int, task_id: int) -> int | None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        self.tasks.complete(task_id, user_id)
        self.journal.create(
            user_id, "task_completed", f"Выполнена задача: {task['title']}", "task", task_id
        )
        if task["repeat_rule"] == "none" or task["due_at"] is None:
            return None
        next_due = add_repeat(parse_iso(task["due_at"]), task["repeat_rule"])
        if next_due is None:
            return None
        next_remind = None
        if task["remind_at"]:
            delta = parse_iso(task["due_at"]) - parse_iso(task["remind_at"])
            next_remind = iso(next_due - delta)
        return self.create_task(
            user_id=user_id,
            title=task["title"],
            due_at=iso(next_due),
            description=task["description"],
            repeat_rule=task["repeat_rule"],
            remind_at=next_remind,
            plot_id=task["plot_id"],
            zone_id=task["zone_id"],
            planting_id=task["planting_id"],
            work_type=task.get("work_type"),
            wait_until_date=task.get("wait_until_date"),
        )

    def today(self, user_id: int, timezone_name: str) -> dict[str, list[dict]]:
        now = utc_now()
        today_start, today_end = local_day_bounds(timezone_name, 0)
        _, three_day_end = local_day_bounds(timezone_name, 3)
        tasks = self.tasks.list_today(user_id, iso(three_day_end))
        overdue: list[dict] = []
        today: list[dict] = []
        upcoming: list[dict] = []
        for task in tasks:
            due = parse_iso(task["due_at"])
            if due < today_start:
                overdue.append(task)
            elif due <= today_end:
                today.append(task)
            elif due <= three_day_end:
                upcoming.append(task)
        return {"overdue": overdue, "today": today, "upcoming": upcoming}

    def snooze_task(self, user_id: int, task_id: int, option: str, timezone_name: str) -> str:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        due_at = iso(snooze_target(option, timezone_name))
        self.tasks.update_status(task_id, user_id, "snoozed", due_at=due_at)
        self.journal.create(user_id, "task_snoozed", f"Отложена задача: {task['title']}", "task", task_id)
        return due_at

    def snooze_task_until(self, user_id: int, task_id: int, due_at: str) -> None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        self.tasks.update_status(task_id, user_id, "snoozed", due_at=due_at)
        self.journal.create(user_id, "task_snoozed", f"Отложена задача: {task['title']}", "task", task_id)

    def skip_task(self, user_id: int, task_id: int, reason: str | None = None) -> int | None:
        task = self.tasks.get(task_id, user_id)
        if task is None:
            raise ValueError("task not found")
        self.tasks.update_status(task_id, user_id, "skipped", skipped_reason=reason)
        note = f"Пропущена задача: {task['title']}"
        if reason:
            note += f". Причина: {reason}"
        self.journal.create(user_id, "task_skipped", note, "task", task_id)
        if task["repeat_rule"] == "none" or task["due_at"] is None:
            return None
        next_due = add_repeat(parse_iso(task["due_at"]), task["repeat_rule"])
        if next_due is None:
            return None
        next_remind = None
        if task["remind_at"]:
            delta = parse_iso(task["due_at"]) - parse_iso(task["remind_at"])
            next_remind = iso(next_due - delta)
        return self.create_task(
            user_id=user_id,
            title=task["title"],
            due_at=iso(next_due),
            description=task["description"],
            repeat_rule=task["repeat_rule"],
            remind_at=next_remind,
            plot_id=task["plot_id"],
            zone_id=task["zone_id"],
            planting_id=task["planting_id"],
            work_type=task.get("work_type"),
            wait_until_date=task.get("wait_until_date"),
        )

    def schedule_due_reminders(self, now=None) -> int:
        now = now or utc_now()
        count = 0
        for task in self.tasks.due_for_reminder(iso(now)):
            settings = self.users.get_settings(task["user_id"])
            user = self.users.conn.execute(
                "SELECT timezone FROM users WHERE id = ?", (task["user_id"],)
            ).fetchone()
            if settings is None or user is None:
                continue
            send_at = quiet_adjusted(
                parse_iso(task["remind_at"]),
                settings["quiet_start"],
                settings["quiet_end"],
                user["timezone"],
            )
            if send_at <= now:
                send_at = now
            self.reminders.create(task["id"], task["user_id"], iso(send_at))
            count += 1
        return count

    def default_remind_at(self, user_id: int, due_at: str) -> str:
        settings = self.users.get_settings(user_id)
        lead = int(settings["reminder_lead_minutes"]) if settings else 60
        return iso(parse_iso(due_at) - timedelta(minutes=lead))

    def preview_due_reminders(self, now=None) -> list[dict]:
        now = now or utc_now()
        pending = self.reminders.list_pending(iso(now))
        due_tasks = self.tasks.due_for_reminder(iso(now))
        return [{"source": "event", **row} for row in pending] + [
            {"source": "task", **row} for row in due_tasks
        ]
