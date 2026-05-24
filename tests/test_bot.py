from __future__ import annotations

import unittest

from ogorodom_bot.bot import BotApplication, IncomingCallback, IncomingMessage, BotResponse, _dispatch_response
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


class FailingEditApi(DummyApi):
    def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup=None):
        raise RuntimeError("edit failed")


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

        self.assertIn("Задача #1 «Полить грядки» создана", created)
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
        self.assertIn("Новая задача", labels)
        self.assertIn("Все задачи", labels)
        self.assertIn("Огород", labels)
        self.assertIn("Настройки", labels)

    def test_tasks_button_opens_task_list(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))

        response = self.bot.handle_message(self.message("Все задачи"))

        self.assertIn("Все открытые задачи", response.text)
        self.assertIn("Полить", response.text)
        self.assertIn("task:done:1", _inline_callbacks(response.reply_markup))
        self.assertIn("tasks:new", _inline_callbacks(response.reply_markup))

    def test_legacy_tasks_button_alias_still_works(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))

        response = self.bot.handle_message(self.message("Задачи"))

        self.assertIn("Все открытые задачи", response.text)
        self.assertIn("Полить", response.text)

    def test_today_command_shows_overdue_today_and_upcoming_actions(self) -> None:
        self.bot.handle(self.message("/task 2026-05-24 12:00 | Просроченная"))
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Сегодня"))
        self.bot.handle(self.message("/task 2026-05-27 12:00 | Скоро"))

        response = self.bot.handle_message(self.message("/today"))

        self.assertIn("Просрочено", response.text)
        self.assertIn("Сегодня", response.text)
        self.assertIn("Ближайшие 3 дня", response.text)
        callbacks = _inline_callbacks(response.reply_markup)
        self.assertIn("task:done:1", callbacks)
        self.assertIn("task:snooze:1", callbacks)
        self.assertIn("task:skip:1", callbacks)
        self.assertIn("task:details:1", callbacks)

    def test_callback_done_completes_task_without_manual_id(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))

        response = self.bot.handle_callback(self.callback("task:done:1"))

        self.assertIn("закрыта", response.text)
        self.assertEqual(response.answer_callback_query_id, "cb1")
        with connect(self.app_state.db_path) as conn:
            task = TaskService(conn).get_task(1, 1)
        self.assertEqual(task["status"], "done")

    def test_snooze_and_skip_callbacks_update_task(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить | repeat=daily"))
        snoozed = self.bot.handle_callback(self.callback("task:snooze1h:1"))
        skipped_menu = self.bot.handle_callback(self.callback("task:skip:1"))
        self.bot.handle_callback(self.callback("task:skipreason:1"))
        skipped = self.bot.handle_message(self.message("Дождь"))

        self.assertIn("отложена", snoozed.text)
        self.assertIn("Пропустить задачу", skipped_menu.text)
        self.assertIn("пропущена", skipped.text)
        with connect(self.app_state.db_path) as conn:
            task = TaskService(conn).get_task(1, 1)
            tasks = TaskService(conn).list_open(1)
        self.assertEqual(task["status"], "skipped")
        self.assertEqual(task["skipped_reason"], "Дождь")
        self.assertEqual(len(tasks), 1)

    def test_settings_notify_callback_toggles_notifications(self) -> None:
        self.bot.handle_message(self.message("/start"))

        response = self.bot.handle_callback(self.callback("settings:notify:toggle"))

        self.assertIn("Уведомления: выключены", response.text)
        with connect(self.app_state.db_path) as conn:
            settings = UserRepository(conn).get_settings(1)
        self.assertEqual(settings["notifications_enabled"], 0)

    def test_pause_and_resume_commands_toggle_notifications(self) -> None:
        pause = self.bot.handle_message(self.message("/pause"))
        resume = self.bot.handle_message(self.message("/resume"))

        self.assertIn("выключены", pause.text)
        self.assertIn("включены", resume.text)
        with connect(self.app_state.db_path) as conn:
            settings = UserRepository(conn).get_settings(1)
        self.assertEqual(settings["notifications_enabled"], 1)

    def test_work_aliases_and_log_create_journal_entries(self) -> None:
        water = self.bot.handle_message(self.message("/water Полил теплицу"))
        mow = self.bot.handle_message(self.message("/mow Покосил траву"))
        treat = self.bot.handle_message(self.message("/treat Обработка от тли wait=3"))
        log = self.bot.handle_message(self.message("/log Ручная запись"))

        self.assertIn("Запись журнала #1", water.text)
        self.assertIn("Запись журнала #2", mow.text)
        self.assertIn("Запись журнала #3", treat.text)
        self.assertIn("Запись журнала #4", log.text)
        with connect(self.app_state.db_path) as conn:
            rows = TaskService(conn).journal.list_recent(1, limit=10)
        self.assertEqual(rows[-1]["work_type"], "watering")
        self.assertEqual(rows[-2]["work_type"], "mowing")
        self.assertEqual(rows[-3]["work_type"], "treatment")
        self.assertIsNotNone(rows[-3]["wait_until_date"])

    def test_log_dialog_creates_entry(self) -> None:
        self.bot.handle_message(self.message("/log"))
        self.bot.handle_callback(self.callback("logtype:watering"))
        response = self.bot.handle_message(self.message("Полив через диалог"))

        self.assertIn("Запись журнала #1", response.text)
        with connect(self.app_state.db_path) as conn:
            rows = TaskService(conn).journal.list_recent(1)
        self.assertEqual(rows[0]["work_type"], "watering")

    def test_delete_me_requires_confirmation_and_deletes_user_data(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Полить"))
        prompt = self.bot.handle_message(self.message("/delete_me"))
        response = self.bot.handle_callback(self.callback("delete:confirm"))

        self.assertIn("Удалить все ваши данные", prompt.text)
        self.assertIn("данные удалены", response.text)
        with connect(self.app_state.db_path) as conn:
            users = UserRepository(conn).list_all()
            tasks = TaskService(conn).list_open(1)
        self.assertEqual(users, [])
        self.assertEqual(tasks, [])

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
        self.assertIn("25.05.2026 12:00", confirm.text)
        self.assertNotIn("T09:00:00", confirm.text)
        self.assertIn("Задача #1 «Полить теплицу» создана", created.text)
        with connect(self.app_state.db_path) as conn:
            state = DialogStateRepository(conn).get(1)
            tasks = TaskService(conn).list_open(1)
        self.assertIsNone(state)
        self.assertEqual(tasks[0]["repeat_rule"], "weekly")

    def test_new_task_button_uses_quick_due_buttons(self) -> None:
        start = self.bot.handle_message(self.message("Новая задача"))
        due_prompt = self.bot.handle_message(self.message("Проверить полив"))
        due = self.bot.handle_callback(self.callback("task:due:tomorrow_morning"))
        self.bot.handle_callback(self.callback("task:repeat:none"))
        created = self.bot.handle_callback(self.callback("task:create"))

        self.assertIn("Новая задача", start.text)
        self.assertIn("Когда нужно сделать", due_prompt.text)
        self.assertIn("task:due:tomorrow_morning", _inline_callbacks(due_prompt.reply_markup))
        self.assertIn("Нужен повтор", due.text)
        self.assertIn("Проверить полив", created.text)
        with connect(self.app_state.db_path) as conn:
            tasks = TaskService(conn).list_open(1)
        self.assertEqual(tasks[0]["title"], "Проверить полив")
        self.assertIsNotNone(tasks[0]["due_at"])

    def test_task_details_allow_editing_title_and_due(self) -> None:
        self.bot.handle(self.message("/task 2026-05-25 12:00 | Старое название"))

        details = self.bot.handle_callback(self.callback("task:details:1"))
        edit_menu = self.bot.handle_callback(self.callback("task:edit:1"))
        self.bot.handle_callback(self.callback("task:edit_title:1"))
        renamed = self.bot.handle_message(self.message("Новое название"))
        self.bot.handle_callback(self.callback("task:edit_due:1"))
        changed_due = self.bot.handle_callback(self.callback("task:due:none"))

        self.assertIn("task:edit:1", _inline_callbacks(details.reply_markup))
        self.assertIn("Что изменить", edit_menu.text)
        self.assertIn("Новое название", renamed.text)
        self.assertIn("без срока", changed_due.text)
        with connect(self.app_state.db_path) as conn:
            task = TaskService(conn).get_task(1, 1)
        self.assertEqual(task["title"], "Новое название")
        self.assertIsNone(task["due_at"])

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

    def test_dispatch_falls_back_to_send_when_edit_fails(self) -> None:
        api = FailingEditApi()
        response = BotResponse(
            chat_id=100,
            text="Обновленный список",
            reply_markup={"inline_keyboard": []},
            edit_message_id=10,
            answer_callback_query_id="cb1",
        )

        with self.assertLogs("ogorodom_bot.bot", level="ERROR"):
            _dispatch_response(api, response)

        self.assertEqual(api.answered[0][0], "cb1")
        self.assertEqual(api.sent[0][1], "Обновленный список")


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
