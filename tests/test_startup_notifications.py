from __future__ import annotations

import unittest
from dataclasses import replace

from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.services.startup_notifications import (
    StartupNotificationService,
    build_startup_update_message,
)
from ogorodom_bot.services.users import UserService
from tests.helpers import TempApp


class DummyApi:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return {"ok": True}


class StartupNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TempApp()
        apply_migrations(self.app.db_path)

    def tearDown(self) -> None:
        self.app.cleanup()

    def test_build_startup_update_message(self) -> None:
        settings = replace(
            self.app.settings,
            app_version="0.6.0-beta",
            startup_update_message=(
                "Добавлено редактирование задач, привязка к участкам и зонам, "
                "а также справочник работ."
            ),
            testing_notice_enabled=True,
            testing_notice_text=(
                "⚠️ Бот находится в бета-тестировании. Данные могут быть изменены или утеряны."
            ),
        )

        message = build_startup_update_message(settings)

        self.assertIn("Бот обновлен до версии 0.6.0-beta", message)
        self.assertIn("Добавлено редактирование задач", message)
        self.assertIn("бета-тестировании", message)
        self.assertIn("Главное меню открыто ниже. Если кнопки не появились, отправьте /start.", message)

    def test_startup_notification_sent_once_per_version(self) -> None:
        settings = replace(
            self.app.settings,
            app_version="0.6.0-beta",
            send_startup_update_on_boot=True,
            startup_update_message="Добавлено уведомление об обновлении.",
            testing_notice_enabled=True,
        )
        api = DummyApi()
        with connect(self.app.db_path) as conn:
            UserService(conn, settings).ensure_user(100, "User")
            first = StartupNotificationService(conn, settings, api).send_once_for_version()
            second = StartupNotificationService(conn, settings, api).send_once_for_version()

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(len(api.sent), 1)
        self.assertIn("0.6.0-beta", api.sent[0][1])
        self.assertIn("Новая задача", _keyboard_labels(api.sent[0][2]))


def _keyboard_labels(markup: dict | None) -> list[str]:
    if not markup:
        return []
    return [button["text"] for row in markup.get("keyboard", []) for button in row]


if __name__ == "__main__":
    unittest.main()
