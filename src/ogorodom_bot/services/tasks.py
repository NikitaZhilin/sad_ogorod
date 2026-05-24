from __future__ import annotations

import sqlite3
from datetime import timedelta

from ogorodom_bot.repositories.tasks import JournalRepository, ReminderRepository, TaskRepository
from ogorodom_bot.repositories.users import UserRepository
from ogorodom_bot.services.time_utils import (
    add_repeat,
    iso,
    parse_iso,
    quiet_adjusted,
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
        )
        self.journal.create(user_id, "task_created", f"Создана задача: {title}", "task", task_id)
        return task_id

    def list_open(self, user_id: int) -> list[dict]:
        return self.tasks.list_open(user_id)

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
