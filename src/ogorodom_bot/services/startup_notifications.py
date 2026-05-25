from __future__ import annotations

import logging
import sqlite3

from ogorodom_bot.config import Settings
from ogorodom_bot.repositories.startup import StartupBroadcastRepository
from ogorodom_bot.repositories.users import UserRepository
from ogorodom_bot.telegram_api import TelegramApi
from ogorodom_bot.ui import keyboards

logger = logging.getLogger(__name__)


class StartupNotificationService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, api: TelegramApi):
        self.conn = conn
        self.settings = settings
        self.api = api
        self.broadcasts = StartupBroadcastRepository(conn)
        self.users = UserRepository(conn)

    def send_once_for_version(self) -> dict[str, int | bool]:
        if not self.settings.send_startup_update_on_boot:
            return {"enabled": False, "sent": 0, "failed": 0}
        if self.broadcasts.get(self.settings.app_version) is not None:
            return {"enabled": True, "sent": 0, "failed": 0}

        message = build_startup_update_message(self.settings)
        sent = 0
        failed = 0
        for user in self.users.list_all():
            try:
                self.api.send_message(
                    int(user["telegram_id"]),
                    message,
                    reply_markup=keyboards.main_menu(),
                )
            except Exception:
                failed += 1
                logger.exception("failed to send startup update user_id=%s", user["id"])
            else:
                sent += 1
        self.broadcasts.create(self.settings.app_version, message, sent, failed)
        return {"enabled": True, "sent": sent, "failed": failed}


def build_startup_update_message(settings: Settings) -> str:
    parts = [f"Бот обновлен до версии {settings.app_version} и перезапущен."]
    if settings.startup_update_message.strip():
        parts.append(settings.startup_update_message.strip())
    if settings.testing_notice_enabled and settings.testing_notice_text.strip():
        parts.append(settings.testing_notice_text.strip())
    parts.append("Главное меню открыто. Используйте кнопки ниже для навигации.")
    return "\n\n".join(parts)
