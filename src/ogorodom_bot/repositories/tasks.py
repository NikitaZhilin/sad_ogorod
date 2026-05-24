from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class TaskRepository(Repository):
    def create(
        self,
        user_id: int,
        title: str,
        description: str | None,
        due_at: str | None,
        repeat_rule: str,
        remind_at: str | None,
        plot_id: int | None = None,
        zone_id: int | None = None,
        planting_id: int | None = None,
        work_type: str | None = None,
        wait_until_date: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO tasks(
                user_id, title, description, due_at, repeat_rule, remind_at,
                plot_id, zone_id, planting_id, work_type, wait_until_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                description,
                due_at,
                repeat_rule,
                remind_at,
                plot_id,
                zone_id,
                planting_id,
                work_type,
                wait_until_date,
            ),
        )
        return int(cur.lastrowid)

    def get(self, task_id: int, user_id: int | None = None) -> dict | None:
        if user_id is None:
            row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
            ).fetchone()
        return self._row_to_dict(row)

    def list_open(self, user_id: int, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status IN ('open', 'active', 'snoozed')
            ORDER BY COALESCE(due_at, '9999-12-31T23:59:59'), id
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def complete(self, task_id: int, user_id: int) -> None:
        self.conn.execute(
            """
            UPDATE tasks
            SET status = 'done', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (task_id, user_id),
        )

    def due_for_reminder(self, now_iso: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('open', 'active', 'snoozed')
              AND remind_at IS NOT NULL
              AND remind_at <= ?
              AND id NOT IN (
                  SELECT task_id FROM reminder_events
                  WHERE status IN ('pending', 'sent')
              )
            ORDER BY remind_at
            """,
            (now_iso,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_today(self, user_id: int, end_iso: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ?
              AND status IN ('open', 'active', 'snoozed')
              AND due_at IS NOT NULL
              AND due_at <= ?
            ORDER BY due_at, id
            LIMIT ?
            """,
            (user_id, end_iso, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_status(
        self,
        task_id: int,
        user_id: int,
        status: str,
        due_at: str | None = None,
        skipped_reason: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                due_at = COALESCE(?, due_at),
                skipped_reason = COALESCE(?, skipped_reason),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (status, due_at, skipped_reason, task_id, user_id),
        )

    def update_task(
        self,
        task_id: int,
        user_id: int,
        *,
        title: str | None = None,
        due_at: str | None = None,
        repeat_rule: str | None = None,
        remind_at: str | None = None,
        clear_due: bool = False,
    ) -> None:
        assignments = ["updated_at = CURRENT_TIMESTAMP"]
        values: list[object] = []
        if title is not None:
            assignments.append("title = ?")
            values.append(title)
        if clear_due:
            assignments.extend(["due_at = NULL", "remind_at = NULL"])
        elif due_at is not None:
            assignments.append("due_at = ?")
            values.append(due_at)
            assignments.append("remind_at = ?")
            values.append(remind_at)
        if repeat_rule is not None:
            assignments.append("repeat_rule = ?")
            values.append(repeat_rule)
        values.extend([task_id, user_id])
        self.conn.execute(
            f"""
            UPDATE tasks
            SET {", ".join(assignments)}
            WHERE id = ? AND user_id = ?
            """,
            values,
        )


class JournalRepository(Repository):
    def create(
        self,
        user_id: int,
        entry_type: str,
        note: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        work_type: str | None = None,
        task_id: int | None = None,
        zone_id: int | None = None,
        planting_id: int | None = None,
        wait_until_date: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO journal_entries(
                user_id, entity_type, entity_id, entry_type, note,
                work_type, task_id, zone_id, planting_id, wait_until_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                entity_type,
                entity_id,
                entry_type,
                note,
                work_type,
                task_id,
                zone_id,
                planting_id,
                wait_until_date,
            ),
        )
        return int(cur.lastrowid)

    def list_recent(self, user_id: int, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM journal_entries
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


class ReminderRepository(Repository):
    def create(self, task_id: int, user_id: int, send_at: str) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO reminder_events(task_id, user_id, send_at)
            VALUES (?, ?, ?)
            """,
            (task_id, user_id, send_at),
        )
        return int(cur.lastrowid)

    def list_pending(self, now_iso: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT re.*, t.title, t.due_at, u.telegram_id
            FROM reminder_events re
            JOIN tasks t ON t.id = re.task_id
            JOIN users u ON u.id = re.user_id
            JOIN user_settings us ON us.user_id = re.user_id
            WHERE re.status = 'pending'
              AND re.send_at <= ?
              AND us.notifications_enabled = 1
            ORDER BY re.send_at, re.id
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_sent(self, event_id: int) -> None:
        self.conn.execute(
            """
            UPDATE reminder_events
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (event_id,),
        )

    def mark_failed(self, event_id: int, error: str) -> None:
        self.conn.execute(
            """
            UPDATE reminder_events
            SET attempts = attempts + 1,
                last_error = ?,
                status = CASE WHEN attempts >= 4 THEN 'failed' ELSE 'pending' END
            WHERE id = ?
            """,
            (error[:500], event_id),
        )
