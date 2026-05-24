from __future__ import annotations

import unittest

from ogorodom_bot.bot import BotApplication, IncomingCallback, IncomingMessage
from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.repositories.dialogs import DialogStateRepository
from ogorodom_bot.repositories.users import UserRepository
from ogorodom_bot.services.garden import GardenService
from ogorodom_bot.services.tasks import TaskService
from tests.helpers import TempApp


class DummyApi:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.answered = []

    def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return {"ok": True}

    def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup=None):
        self.edited.append((chat_id, message_id, text, reply_markup))
        return {"ok": True}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None):
        self.answered.append((callback_query_id, text))
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

    def callback(self, data: str) -> IncomingCallback:
        return IncomingCallback(
            update_id=2,
            callback_query_id="cb1",
            chat_id=100,
            message_id=10,
            telegram_id=100,
            full_name="User",
            data=data,
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

    def test_legacy_garden_and_settings_commands_still_work(self) -> None:
        plot = self.bot.handle(self.message("/plot Север"))
        plots = self.bot.handle(self.message("/plots"))
        zone = self.bot.handle(self.message("/zone Теплица"))
        zones = self.bot.handle(self.message("/zones"))
        planting = self.bot.handle(self.message("/planting Томат | Черри | 2026-05-25"))
        plantings = self.bot.handle(self.message("/plantings"))
        quiet = self.bot.handle(self.message("/settings quiet 21:00 07:00"))
        notify = self.bot.handle(self.message("/settings notify off"))

        self.assertIn("Участок #1 добавлен", plot)
        self.assertIn("Север", plots)
        self.assertIn("Зона #1 добавлена", zone)
        self.assertIn("Теплица", zones)
        self.assertIn("Посадка #1 добавлена", planting)
        self.assertIn("Томат", plantings)
        self.assertIn("Quiet hours обновлены", quiet)
        self.assertIn("Уведомления выключены", notify)

    def test_start_shows_main_menu(self) -> None:
        response = self.bot.handle_message(self.message("/start"))

        self.assertIn("Огородом", response.text)
        self.assertIsNotNone(response.reply_markup)
        labels = _keyboard_labels(response.reply_markup)
        self.assertIn("Задачи", labels)
        self.assertIn("Огород", labels)
        self.assertIn("Настройки", labels)

    def test_tasks_button_opens_task_list(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))

        response = self.bot.handle_message(self.message("Задачи"))

        self.assertIn("Открытые задачи", response.text)
        self.assertIn("Полить", response.text)
        self.assertIn("task:done:1", _inline_callbacks(response.reply_markup))
        self.assertIn("tasks:new", _inline_callbacks(response.reply_markup))

    def test_callback_done_completes_task_without_manual_id(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))

        response = self.bot.handle_callback(self.callback("task:done:1"))

        self.assertIn("закрыта", response.text)
        self.assertEqual(response.answer_callback_query_id, "cb1")
        with connect(self.app_state.db_path) as conn:
            task = TaskService(conn).get_task(1, 1)
        self.assertEqual(task["status"], "done")

    def test_settings_notify_callback_toggles_notifications(self) -> None:
        self.bot.handle_message(self.message("/start"))

        response = self.bot.handle_callback(self.callback("settings:notify:toggle"))

        self.assertIn("Уведомления: выключены", response.text)
        with connect(self.app_state.db_path) as conn:
            settings = UserRepository(conn).get_settings(1)
        self.assertEqual(settings["notifications_enabled"], 0)

    def test_task_dialog_saves_and_clears_state(self) -> None:
        self.bot.handle_message(self.message("/start"))
        self.bot.handle_callback(self.callback("tasks:new"))
        self.bot.handle_message(self.message("Полить теплицу"))

        with connect(self.app_state.db_path) as conn:
            state = DialogStateRepository(conn).get(1)
        self.assertEqual(state["state"], "task_wait_due_at")

        self.bot.handle_message(self.message("2026-05-25 12:00"))
        confirm = self.bot.handle_callback(self.callback("task:repeat:weekly"))
        created = self.bot.handle_callback(self.callback("task:create"))

        self.assertIn("Полить теплицу", confirm.text)
        self.assertIn("Задача #1 создана", created.text)
        with connect(self.app_state.db_path) as conn:
            state = DialogStateRepository(conn).get(1)
            tasks = TaskService(conn).list_open(1)
        self.assertIsNone(state)
        self.assertEqual(tasks[0]["repeat_rule"], "weekly")

    def test_cancel_clears_dialog_state(self) -> None:
        self.bot.handle_message(self.message("/start"))
        self.bot.handle_callback(self.callback("tasks:new"))
        response = self.bot.handle_message(self.message("Отмена"))

        self.assertIn("отменено", response.text)
        with connect(self.app_state.db_path) as conn:
            self.assertIsNone(DialogStateRepository(conn).get(1))

    def test_garden_dialogs_create_plot_zone_and_planting(self) -> None:
        self.bot.handle_message(self.message("/start"))
        self.bot.handle_callback(self.callback("plot:add"))
        self.bot.handle_message(self.message("Север"))
        self.bot.handle_callback(self.callback("zone:add"))
        self.bot.handle_message(self.message("Теплица"))
        self.bot.handle_callback(self.callback("zone:plot:1"))
        self.bot.handle_callback(self.callback("planting:add"))
        self.bot.handle_message(self.message("Томат"))
        self.bot.handle_message(self.message("Черри"))
        self.bot.handle_message(self.message("2026-05-25"))
        self.bot.handle_callback(self.callback("planting:zone:1"))

        with connect(self.app_state.db_path) as conn:
            garden = GardenService(conn)
            plots = garden.list_plots(1)
            zones = garden.list_zones(1)
            plantings = garden.list_plantings(1)

        self.assertEqual(plots[0]["name"], "Север")
        self.assertEqual(zones[0]["plot_id"], 1)
        self.assertEqual(plantings[0]["zone_id"], 1)
        self.assertEqual(plantings[0]["variety"], "Черри")


def _keyboard_labels(markup: dict | None) -> list[str]:
    if not markup:
        return []
    return [button["text"] for row in markup.get("keyboard", []) for button in row]


def _inline_callbacks(markup: dict | None) -> list[str]:
    if not markup:
        return []
    return [
        button["callback_data"]
        for row in markup.get("inline_keyboard", [])
        for button in row
    ]


if __name__ == "__main__":
    unittest.main()
