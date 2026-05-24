from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class UserRepository(Repository):
    def get_by_telegram_id(self, telegram_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def create(self, telegram_id: int, full_name: str | None, timezone: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO users(telegram_id, full_name, timezone) VALUES (?, ?, ?)",
            (telegram_id, full_name, timezone),
        )
        return int(cur.lastrowid)

    def update_name(self, user_id: int, full_name: str | None) -> None:
        self.conn.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name, user_id))

    def get_settings(self, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def create_settings(
        self,
        user_id: int,
        quiet_start: str,
        quiet_end: str,
        reminder_lead_minutes: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO user_settings(
                user_id, quiet_start, quiet_end, reminder_lead_minutes
            ) VALUES (?, ?, ?, ?)
            """,
            (user_id, quiet_start, quiet_end, reminder_lead_minutes),
        )

    def update_settings(
        self,
        user_id: int,
        quiet_start: str | None = None,
        quiet_end: str | None = None,
        reminder_lead_minutes: int | None = None,
        notifications_enabled: bool | None = None,
    ) -> None:
        current = self.get_settings(user_id)
        if current is None:
            raise ValueError("settings not found")
        self.conn.execute(
            """
            UPDATE user_settings
            SET quiet_start = ?, quiet_end = ?, reminder_lead_minutes = ?,
                notifications_enabled = ?
            WHERE user_id = ?
            """,
            (
                quiet_start if quiet_start is not None else current["quiet_start"],
                quiet_end if quiet_end is not None else current["quiet_end"],
                reminder_lead_minutes
                if reminder_lead_minutes is not None
                else current["reminder_lead_minutes"],
                int(notifications_enabled)
                if notifications_enabled is not None
                else current["notifications_enabled"],
                user_id,
            ),
        )
