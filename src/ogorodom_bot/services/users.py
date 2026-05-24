from __future__ import annotations

import sqlite3

from ogorodom_bot.config import Settings
from ogorodom_bot.repositories.users import UserRepository


class UserService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.repo = UserRepository(conn)
        self.settings = settings

    def ensure_user(self, telegram_id: int, full_name: str | None) -> dict:
        user = self.repo.get_by_telegram_id(telegram_id)
        if user is None:
            user_id = self.repo.create(
                telegram_id=telegram_id,
                full_name=full_name,
                timezone=self.settings.default_timezone,
            )
            self.repo.create_settings(
                user_id=user_id,
                quiet_start=self.settings.default_quiet_start,
                quiet_end=self.settings.default_quiet_end,
                reminder_lead_minutes=self.settings.reminder_lead_minutes,
            )
            user = self.repo.get_by_telegram_id(telegram_id)
        else:
            self.repo.update_name(user["id"], full_name)
        assert user is not None
        return user

    def settings_for(self, user_id: int) -> dict:
        value = self.repo.get_settings(user_id)
        if value is None:
            self.repo.create_settings(
                user_id,
                self.settings.default_quiet_start,
                self.settings.default_quiet_end,
                self.settings.reminder_lead_minutes,
            )
            value = self.repo.get_settings(user_id)
        assert value is not None
        return value

    def update_settings(
        self,
        user_id: int,
        quiet_start: str | None = None,
        quiet_end: str | None = None,
        reminder_lead_minutes: int | None = None,
        notifications_enabled: bool | None = None,
    ) -> None:
        self.repo.update_settings(
            user_id,
            quiet_start=quiet_start,
            quiet_end=quiet_end,
            reminder_lead_minutes=reminder_lead_minutes,
            notifications_enabled=notifications_enabled,
        )
