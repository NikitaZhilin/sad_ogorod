from __future__ import annotations

import unittest

from ogorodom_bot.bot import BotApplication, IncomingMessage
from ogorodom_bot.db.migrations import apply_migrations
from tests.helpers import TempApp


class DummyApi:
    def send_message(self, chat_id: int, text: str):
        return {"ok": True}


class BotHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_state = TempApp()
        apply_migrations(self.app_state.db_path)
        self.bot = BotApplication(self.app_state.settings, DummyApi())

    def tearDown(self) -> None:
        self.app_state.cleanup()

    def message(self, text: str) -> IncomingMessage:
        return IncomingMessage(
            update_id=1,
            chat_id=100,
            telegram_id=100,
            full_name="User",
            text=text,
        )

    def test_create_and_complete_task_via_command(self) -> None:
        created = self.bot.handle(
            self.message("/task 2026-05-25 12:00 | Полить грядки | repeat=daily")
        )
        tasks = self.bot.handle(self.message("/tasks"))
        done = self.bot.handle(self.message("/done 1"))

        self.assertIn("Задача #1 создана", created)
        self.assertIn("Полить грядки", tasks)
        self.assertIn("создан повтор #2", done)


if __name__ == "__main__":
    unittest.main()
