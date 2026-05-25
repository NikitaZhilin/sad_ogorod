from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ogorodom_bot.config import Settings
from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.logging_config import configure_logging
from ogorodom_bot.services.backup import BackupService
from ogorodom_bot.services.diagnostics import DiagnosticsService
from ogorodom_bot.services.dialogs import DialogStateService
from ogorodom_bot.services.garden import GardenService
from ogorodom_bot.services.journal import JournalService, WORK_TYPE_TITLES
from ogorodom_bot.services.privacy import PrivacyService
from ogorodom_bot.services.startup_notifications import StartupNotificationService
from ogorodom_bot.services.startup_backup import StartupBackupService
from ogorodom_bot.services.tasks import TaskService
from ogorodom_bot.services.time_utils import (
    format_month,
    format_local_datetime,
    iso,
    parse_local_datetime,
    parse_planting_date,
    parse_wait_until,
)
from ogorodom_bot.services.users import UserService
from ogorodom_bot.telegram_api import TelegramApi
from ogorodom_bot.ui import keyboards, messages

logger = logging.getLogger(__name__)


HELP = """Огородом

Основной режим - кнопки внизу:
Сегодня - ближайшие дела.
Новая задача - добавить задачу без команды.
Все задачи - список и действия по задачам.
Огород - участки, зоны и насаждения.
Журнал - записи работ.
Настройки - уведомления и тихие часы.

Команды тоже работают:
/today, /task, /tasks, /done, /water, /mow, /treat, /log, /pause, /resume.

Служебные команды:
/backup, /diag, /delete_me."""

MAIN_BUTTONS = {
    "Сегодня",
    "Новая задача",
    "Все задачи",
    "Задачи",
    "Огород",
    "Журнал",
    "Справочник",
    "Настройки",
    "Помощь",
}
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass
class IncomingMessage:
    update_id: int
    chat_id: int
    telegram_id: int
    full_name: str
    text: str


@dataclass
class IncomingCallback:
    update_id: int
    callback_query_id: str
    chat_id: int
    message_id: int
    telegram_id: int
    full_name: str
    data: str


@dataclass
class BotResponse:
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None
    edit_message_id: int | None = None
    answer_callback_query_id: str | None = None
    callback_text: str | None = None


def parse_message(update: dict[str, Any]) -> IncomingMessage | None:
    message = update.get("message") or {}
    text = message.get("text")
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    if not text or "id" not in chat or "id" not in user:
        return None
    full_name = " ".join(
        part for part in [user.get("first_name"), user.get("last_name")] if part
    )
    return IncomingMessage(
        update_id=update["update_id"],
        chat_id=int(chat["id"]),
        telegram_id=int(user["id"]),
        full_name=full_name,
        text=text.strip(),
    )


def parse_callback(update: dict[str, Any]) -> IncomingCallback | None:
    callback = update.get("callback_query") or {}
    data = callback.get("data")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    user = callback.get("from") or {}
    if not data or "id" not in callback or "id" not in chat or "message_id" not in message:
        return None
    full_name = " ".join(
        part for part in [user.get("first_name"), user.get("last_name")] if part
    )
    return IncomingCallback(
        update_id=update["update_id"],
        callback_query_id=str(callback["id"]),
        chat_id=int(chat["id"]),
        message_id=int(message["message_id"]),
        telegram_id=int(user["id"]),
        full_name=full_name,
        data=data,
    )


class BotApplication:
    def __init__(self, settings: Settings, api: TelegramApi):
        self.settings = settings
        self.api = api

    def handle(self, message: IncomingMessage) -> str:
        return self.handle_message(message).text

    def handle_message(self, message: IncomingMessage) -> BotResponse:
        with connect(self.settings.database_path) as conn:
            user_service = UserService(conn, self.settings)
            user = user_service.ensure_user(message.telegram_id, message.full_name)
            dialog = DialogStateService(conn)
            text = message.text.strip()

            if text == "Отмена":
                dialog.clear(user["id"])
                return BotResponse(
                    message.chat_id,
                    "Действие отменено.",
                    reply_markup=keyboards.main_menu(),
                )

            if text.startswith("/"):
                return self._handle_command(conn, user_service, user, message.chat_id, text)

            state = dialog.get(user["id"])
            if state and text not in MAIN_BUTTONS:
                return self._handle_dialog_input(conn, user, message.chat_id, text, state)
            if state and text in MAIN_BUTTONS:
                dialog.clear(user["id"])

            if text == "Новая задача":
                return self._start_task_dialog(conn, user["id"], message.chat_id)
            if text in {"Задачи", "Все задачи"}:
                return self._tasks_response(conn, user["id"], message.chat_id)
            if text == "Сегодня":
                return self._today_response(conn, user, message.chat_id)
            if text == "Огород":
                return BotResponse(message.chat_id, messages.garden_home(), keyboards.garden_menu())
            if text == "Журнал":
                return self._journal_response(conn, user["id"], message.chat_id)
            if text == "Справочник":
                return BotResponse(message.chat_id, messages.reference_home(), keyboards.reference_menu())
            if text == "Настройки":
                return self._settings_response(conn, user_service, user, message.chat_id)
            if text == "Помощь":
                return BotResponse(message.chat_id, HELP, keyboards.main_menu())

            return BotResponse(message.chat_id, "Неизвестная команда. /help", keyboards.main_menu())

    def handle_callback(self, callback: IncomingCallback) -> BotResponse:
        with connect(self.settings.database_path) as conn:
            user_service = UserService(conn, self.settings)
            user = user_service.ensure_user(callback.telegram_id, callback.full_name)
            data = callback.data

            response = self._handle_callback_data(
                conn, user_service, user, callback.chat_id, callback.message_id, data
            )
            response.answer_callback_query_id = callback.callback_query_id
            if response.callback_text is None:
                response.callback_text = "Готово"
            return response

    def _handle_command(
        self, conn, user_service: UserService, user: dict, chat_id: int, text: str
    ) -> BotResponse:
        if text == "/start":
            return BotResponse(chat_id, messages.welcome(), keyboards.main_menu())
        if text == "/help":
            return BotResponse(chat_id, HELP, keyboards.main_menu())
        if text == "/today":
            return self._today_response(conn, user, chat_id)
        if text == "/pause":
            user_service.update_settings(user["id"], notifications_enabled=False)
            return BotResponse(chat_id, "Уведомления выключены.")
        if text == "/resume":
            user_service.update_settings(user["id"], notifications_enabled=True)
            return BotResponse(chat_id, "Уведомления включены.")
        if text == "/delete_me":
            return BotResponse(
                chat_id,
                "Удалить все ваши данные? Действие нельзя отменить.",
                keyboards.delete_me_confirm(),
            )
        if text == "/log":
            DialogStateService(conn).set(user["id"], "log_wait_type", {})
            return BotResponse(chat_id, "Выберите тип работы.", keyboards.work_type_menu())
        if text.startswith("/log "):
            entry_id = JournalService(conn).create_entry(
                user["id"], text[len("/log ") :].strip(), work_type="other"
            )
            return BotResponse(chat_id, f"Запись журнала #{entry_id} добавлена.")
        for command, work_type in (
            ("/water", "watering"),
            ("/mow", "mowing"),
            ("/treat", "treatment"),
        ):
            if text == command:
                payload = {"work_type": work_type}
                state = "work_wait_wait_until" if work_type == "treatment" else "work_wait_note"
                DialogStateService(conn).set(user["id"], state, payload)
                prompt = (
                    "Введите срок ожидания после обработки: дату или количество дней. "
                    "Можно '-' если срока ожидания нет."
                    if work_type == "treatment"
                    else f"Введите заметку для работы: {WORK_TYPE_TITLES[work_type]}."
                )
                return BotResponse(chat_id, prompt, keyboards.cancel_inline())
            if text.startswith(command + " "):
                return self._quick_work_log(conn, user, chat_id, work_type, text[len(command) :].strip())
        if text.startswith("/task "):
            return BotResponse(chat_id, self._create_task(conn, user, text[len("/task ") :]))
        if text == "/tasks":
            return BotResponse(chat_id, self._list_tasks(conn, user["id"]))
        if text.startswith("/done "):
            return BotResponse(chat_id, self._done_task(conn, user["id"], text[len("/done ") :]))
        if text.startswith("/plot "):
            plot_id = GardenService(conn).add_plot(user["id"], text[len("/plot ") :].strip())
            return BotResponse(chat_id, f"Участок #{plot_id} добавлен")
        if text == "/plots":
            return BotResponse(
                chat_id, self._format_items(GardenService(conn).list_plots(user["id"]), "Участки")
            )
        if text.startswith("/zone "):
            zone_id = GardenService(conn).add_zone(user["id"], text[len("/zone ") :].strip())
            return BotResponse(chat_id, f"Зона #{zone_id} добавлена")
        if text == "/zones":
            return BotResponse(
                chat_id, self._format_items(GardenService(conn).list_zones(user["id"]), "Зоны")
            )
        if text.startswith("/planting "):
            return BotResponse(
                chat_id, self._create_planting(conn, user, text[len("/planting ") :])
            )
        if text == "/plantings":
            return BotResponse(
                chat_id,
                self._format_items(GardenService(conn).list_plantings(user["id"]), "Насаждения"),
            )
        if text == "/journal":
            return BotResponse(chat_id, self._journal(conn, user["id"]))
        if text.startswith("/settings "):
            return BotResponse(
                chat_id, self._settings(user_service, user["id"], text[len("/settings ") :])
            )
        if text == "/backup":
            path = BackupService(conn, self.settings.database_path, self.settings.backup_dir).create_backup()
            return BotResponse(chat_id, f"Backup создан: {path.name}")
        if text == "/diag":
            return BotResponse(chat_id, self._diag(conn))
        return BotResponse(chat_id, "Неизвестная команда. /help", keyboards.main_menu())

    def _handle_callback_data(
        self,
        conn,
        user_service: UserService,
        user: dict,
        chat_id: int,
        message_id: int,
        data: str,
    ) -> BotResponse:
        dialog = DialogStateService(conn)
        garden = GardenService(conn)

        if data == "dialog:cancel":
            dialog.clear(user["id"])
            return BotResponse(chat_id, "Действие отменено.", keyboards.main_menu())
        if data in {"menu:tasks", "tasks:refresh"}:
            return self._tasks_response(conn, user["id"], chat_id, edit_message_id=message_id)
        if data in {"menu:today", "today:refresh"}:
            return self._today_response(conn, user, chat_id, edit_message_id=message_id)
        if data == "menu:main":
            return BotResponse(chat_id, "Главное меню.", keyboards.main_menu(), callback_text="Меню")
        if data == "menu:garden":
            return BotResponse(chat_id, messages.garden_home(), keyboards.garden_menu(), message_id)
        if data == "menu:reference":
            return BotResponse(
                chat_id,
                messages.reference_home(),
                keyboards.reference_menu(),
                message_id,
                callback_text="Справочник",
            )
        if data == "journal:refresh":
            return self._journal_response(conn, user["id"], chat_id, edit_message_id=message_id)
        if data == "tasks:new":
            response = self._start_task_dialog(conn, user["id"], chat_id)
            response.callback_text = "Введите название"
            return response
        if data.startswith("task:details:"):
            task_id = int(data.rsplit(":", 1)[1])
            task = TaskService(conn).get_task(user["id"], task_id)
            if task is None:
                return self._tasks_response(conn, user["id"], chat_id, edit_message_id=message_id)
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]),
                keyboards.task_details(task_id),
                message_id,
            )
        if data.startswith("task:edit:"):
            task_id = int(data.rsplit(":", 1)[1])
            task = TaskService(conn).get_task(user["id"], task_id)
            if task is None:
                return self._tasks_response(conn, user["id"], chat_id, edit_message_id=message_id)
            return BotResponse(
                chat_id,
                f"Что изменить в задаче #{task_id}?\n{task['title']}",
                keyboards.task_edit_menu(task_id),
                message_id,
            )
        if data.startswith("task:edit_title:"):
            task_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "task_edit_title", {"task_id": task_id})
            return BotResponse(chat_id, "Введите новое название задачи.", keyboards.cancel_inline())
        if data.startswith("task:edit_due:"):
            task_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "task_edit_due_at", {"task_id": task_id})
            return BotResponse(
                chat_id,
                "Когда нужно сделать задачу?\n\nЭта кнопка меняет дату и время выполнения, по которым задача попадает в «Сегодня» и получает напоминание.",
                keyboards.task_due_menu(),
            )
        if data.startswith("task:edit_desc:"):
            task_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "task_edit_description", {"task_id": task_id})
            return BotResponse(
                chat_id,
                "Введите новое описание задачи. Чтобы очистить описание, отправьте '-'.",
                keyboards.cancel_inline(),
            )
        if data.startswith("task:edit_loc:"):
            task_id = int(data.rsplit(":", 1)[1])
            zones = garden.list_zones(user["id"])
            plots = garden.list_plots(user["id"])
            plantings = garden.list_plantings(user["id"])
            return BotResponse(
                chat_id,
                "Выберите насаждение, участок или зону для задачи.",
                keyboards.edit_task_location_menu_with_plantings(
                    task_id, zones, plots, plantings
                ),
            )
        if data.startswith("task:edit_repeat:"):
            task_id = int(data.rsplit(":", 1)[1])
            return BotResponse(chat_id, "Выберите новый повтор задачи.", keyboards.edit_repeat_menu(task_id), message_id)
        if data.startswith("task:er:"):
            _, _, task_raw, repeat_rule = data.split(":", 3)
            task_id = int(task_raw)
            try:
                TaskService(conn).update_repeat_rule(user["id"], task_id, repeat_rule)
            except ValueError:
                return BotResponse(chat_id, "Задача не найдена.", keyboards.main_menu())
            task = TaskService(conn).get_task(user["id"], task_id)
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]) if task else "Повтор обновлен.",
                keyboards.task_details(task_id),
                message_id,
                callback_text="Повтор обновлен",
            )
        if data.startswith("task:due:"):
            option = data.rsplit(":", 1)[1]
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] not in {"task_wait_due_at", "task_edit_due_at"}:
                return BotResponse(chat_id, "Диалог задачи не найден.", keyboards.main_menu())
            if option == "custom":
                return BotResponse(chat_id, "Введите дату сообщением. Например: завтра 9:00 или 25.05.2026 12:00.", keyboards.cancel_inline())
            due_at = _due_at_from_option(option, user["timezone"])
            payload = dict(dialog_state["payload"])
            if dialog_state["state"] == "task_edit_due_at":
                TaskService(conn).update_due_at(user["id"], int(payload["task_id"]), due_at)
                dialog.clear(user["id"])
                task = TaskService(conn).get_task(user["id"], int(payload["task_id"]))
                return BotResponse(
                    chat_id,
                    messages.task_card(task, user["timezone"]) if task else "Дата задачи обновлена.",
                    keyboards.task_details(int(payload["task_id"])),
                    callback_text="Дата обновлена",
                )
            payload["due_at"] = due_at
            if due_at is None:
                payload["repeat_rule"] = "none"
                dialog.set(user["id"], "task_wait_description", payload)
                return BotResponse(
                    chat_id,
                    "Добавьте описание задачи или пропустите этот шаг.",
                    keyboards.task_description_menu(),
                )
            dialog.set(user["id"], "task_wait_repeat", payload)
            return BotResponse(chat_id, "Нужен повтор?", keyboards.repeat_menu())
        if data == "task:desc:skip":
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "task_wait_description":
                return BotResponse(chat_id, "Диалог задачи не найден.", keyboards.main_menu())
            payload = dict(dialog_state["payload"])
            payload["description"] = None
            return self._task_location_step(conn, user, chat_id, payload)
        if data.startswith("task:loc:"):
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "task_wait_location":
                return BotResponse(chat_id, "Диалог задачи не найден.", keyboards.main_menu())
            payload = dict(dialog_state["payload"])
            self._apply_location_payload(conn, user["id"], payload, data)
            dialog.set(user["id"], "task_wait_confirm", payload)
            return BotResponse(
                chat_id,
                messages.task_confirmation(payload, user["timezone"]),
                keyboards.task_confirm(),
            )
        if data.startswith("task:eloc:"):
            parts = data.split(":")
            task_id = int(parts[2])
            try:
                plot_id, zone_id, planting_id = self._parse_location_callback(
                    conn, user["id"], parts[3:]
                )
                TaskService(conn).update_location(
                    user["id"], task_id, plot_id, zone_id, planting_id
                )
            except ValueError:
                return BotResponse(chat_id, "Не удалось изменить место задачи.", keyboards.main_menu())
            task = TaskService(conn).get_task(user["id"], task_id)
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]) if task else "Место обновлено.",
                keyboards.task_details(task_id),
                message_id,
                callback_text="Место обновлено",
            )
        if data.startswith("task:done:"):
            task_id = int(data.rsplit(":", 1)[1])
            try:
                next_id = TaskService(conn).complete_task(user["id"], task_id)
            except ValueError:
                text = "Задача не найдена."
            else:
                text = f"Задача #{task_id} закрыта."
                if next_id:
                    text += f" Создан повтор #{next_id}."
            tasks = TaskService(conn).list_open(user["id"])
            return BotResponse(
                chat_id,
                text + "\n\n" + messages.tasks_list(tasks, user["timezone"]),
                keyboards.tasks_menu(tasks),
                message_id,
            )
        if data.startswith("task:snooze:"):
            task_id = int(data.rsplit(":", 1)[1])
            return BotResponse(chat_id, "На когда отложить задачу?", keyboards.snooze_menu(task_id), message_id)
        for prefix, option in (
            ("task:snooze1h:", "1h"),
            ("task:snoozeevening:", "evening"),
            ("task:snoozetomorrow:", "tomorrow"),
        ):
            if data.startswith(prefix):
                task_id = int(data.rsplit(":", 1)[1])
                due_at = TaskService(conn).snooze_task(user["id"], task_id, option, user["timezone"])
                return BotResponse(
                    chat_id,
                    f"Задача отложена до {format_local_datetime(due_at, user['timezone'])}.",
                    keyboards.main_menu(),
                    callback_text="Отложено",
                )
        if data.startswith("task:snoozecustom:"):
            task_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "task_wait_snooze_at", {"task_id": task_id})
            return BotResponse(
                chat_id,
                "Введите новую дату/время задачи.",
                keyboards.cancel_inline(),
                callback_text="Введите дату",
            )
        if data.startswith("task:skip:"):
            task_id = int(data.rsplit(":", 1)[1])
            return BotResponse(chat_id, "Пропустить задачу?", keyboards.skip_menu(task_id), message_id)
        if data.startswith("task:skipnow:"):
            task_id = int(data.rsplit(":", 1)[1])
            next_id = TaskService(conn).skip_task(user["id"], task_id)
            text = "Задача пропущена."
            if next_id:
                text += f" Создан следующий повтор #{next_id}."
            return BotResponse(chat_id, text, keyboards.main_menu(), callback_text="Пропущено")
        if data.startswith("task:skipreason:"):
            task_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "task_wait_skip_reason", {"task_id": task_id})
            return BotResponse(chat_id, "Введите причину пропуска.", keyboards.cancel_inline())
        if data.startswith("task:repeat:"):
            repeat_rule = data.rsplit(":", 1)[1]
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "task_wait_repeat":
                return BotResponse(chat_id, "Диалог создания задачи не найден.", keyboards.main_menu())
            payload = dict(dialog_state["payload"])
            payload["repeat_rule"] = repeat_rule
            dialog.set(user["id"], "task_wait_description", payload)
            return BotResponse(
                chat_id,
                "Добавьте описание задачи или пропустите этот шаг.\n\nНапример: проверить влажность почвы, пролить без удобрений.",
                keyboards.task_description_menu(),
            )
        if data == "task:create":
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "task_wait_confirm":
                return BotResponse(chat_id, "Диалог создания задачи не найден.", keyboards.main_menu())
            payload = dialog_state["payload"]
            service = TaskService(conn)
            remind_at = (
                service.default_remind_at(user["id"], payload["due_at"])
                if payload.get("due_at")
                else None
            )
            task_id = service.create_task(
                user_id=user["id"],
                title=payload["title"],
                description=payload.get("description"),
                due_at=payload.get("due_at"),
                repeat_rule=payload.get("repeat_rule", "none"),
                remind_at=remind_at,
                plot_id=payload.get("plot_id"),
                zone_id=payload.get("zone_id"),
                planting_id=payload.get("planting_id"),
            )
            dialog.clear(user["id"])
            return BotResponse(
                chat_id,
                f"Задача #{task_id} «{payload['title']}» создана.",
                keyboards.main_menu(),
                callback_text="Задача создана",
            )
        if data == "garden:plots":
            plots = garden.list_plots(user["id"])
            return BotResponse(
                chat_id,
                messages.garden_items("Участки", plots),
                keyboards.garden_list("plots", plots),
                message_id,
            )
        if data == "garden:zones":
            zones = garden.list_zones(user["id"])
            return BotResponse(
                chat_id,
                messages.garden_items("Зоны", zones),
                keyboards.garden_list("zones", zones),
                message_id,
            )
        if data == "garden:plantings":
            plantings = garden.list_plantings(user["id"])
            return BotResponse(
                chat_id,
                messages.garden_items("Насаждения", plantings),
                keyboards.garden_list("plantings", plantings),
                message_id,
            )
        if data.startswith("planting:details:"):
            planting_id = int(data.rsplit(":", 1)[1])
            planting = garden.get_planting(user["id"], planting_id)
            if planting is None:
                return BotResponse(chat_id, "Насаждение не найдено.", keyboards.garden_menu())
            return BotResponse(
                chat_id,
                messages.planting_card(planting),
                keyboards.planting_details(planting_id),
                message_id,
            )
        if data.startswith("plot:details:"):
            plot_id = int(data.rsplit(":", 1)[1])
            plot = garden.get_plot(user["id"], plot_id)
            if plot is None:
                return BotResponse(chat_id, "Участок не найден.", keyboards.garden_menu())
            return BotResponse(
                chat_id,
                messages.plot_card(plot, garden.list_zones(user["id"])),
                keyboards.plot_details(plot_id),
                message_id,
            )
        if data.startswith("plot:edit:"):
            plot_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "plot_edit_name", {"plot_id": plot_id})
            return BotResponse(chat_id, "Введите новое название участка.", keyboards.cancel_inline())
        if data.startswith("plot:delete_confirm:"):
            plot_id = int(data.rsplit(":", 1)[1])
            try:
                garden.delete_plot(user["id"], plot_id)
            except ValueError:
                return BotResponse(chat_id, "Участок не найден.", keyboards.garden_menu())
            return BotResponse(chat_id, "Участок удален. Зоны и задачи отвязаны от него.", keyboards.garden_menu())
        if data.startswith("plot:delete:"):
            plot_id = int(data.rsplit(":", 1)[1])
            return BotResponse(
                chat_id,
                "Удалить участок? Зоны и задачи не удалятся, но потеряют привязку к участку.",
                keyboards.confirm_delete_plot(plot_id),
                message_id,
            )
        if data.startswith("zone:details:"):
            zone_id = int(data.rsplit(":", 1)[1])
            zone = garden.get_zone(user["id"], zone_id)
            if zone is None:
                return BotResponse(chat_id, "Зона не найдена.", keyboards.garden_menu())
            return BotResponse(chat_id, messages.zone_card(zone), keyboards.zone_details(zone_id), message_id)
        if data.startswith("zone:edit:"):
            zone_id = int(data.rsplit(":", 1)[1])
            dialog.set(user["id"], "zone_edit_name", {"zone_id": zone_id})
            return BotResponse(chat_id, "Введите новое название зоны.", keyboards.cancel_inline())
        if data.startswith("zone:delete_confirm:"):
            zone_id = int(data.rsplit(":", 1)[1])
            try:
                garden.delete_zone(user["id"], zone_id)
            except ValueError:
                return BotResponse(chat_id, "Зона не найдена.", keyboards.garden_menu())
            return BotResponse(chat_id, "Зона удалена. Насаждения и задачи отвязаны от нее.", keyboards.garden_menu())
        if data.startswith("zone:delete:"):
            zone_id = int(data.rsplit(":", 1)[1])
            return BotResponse(
                chat_id,
                "Удалить зону? Насаждения и задачи не удалятся, но потеряют привязку к зоне.",
                keyboards.confirm_delete_zone(zone_id),
                message_id,
            )
        if data == "plot:add":
            dialog.set(user["id"], "plot_wait_name", {})
            return BotResponse(chat_id, "Введите название участка.", keyboards.cancel_inline())
        if data == "zone:add":
            dialog.set(user["id"], "zone_wait_name", {})
            return BotResponse(chat_id, "Введите название зоны.", keyboards.cancel_inline())
        if data.startswith("zone:plot:"):
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "zone_wait_plot":
                return BotResponse(chat_id, "Диалог создания зоны не найден.", keyboards.main_menu())
            plot_raw = data.rsplit(":", 1)[1]
            plot_id = None if plot_raw == "none" else int(plot_raw)
            zone_id = garden.add_zone(user["id"], dialog_state["payload"]["name"], plot_id=plot_id)
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Зона #{zone_id} добавлена.", keyboards.main_menu())
        if data == "planting:add":
            dialog.set(user["id"], "planting_wait_type", {})
            return BotResponse(
                chat_id,
                "Что добавляем?\n\nОвощи/ягоды - клубника, помидоры, огурцы и другие культуры.",
                keyboards.plant_type_menu(),
            )
        if data.startswith("planttype:"):
            plant_type = data.rsplit(":", 1)[1]
            dialog.set(user["id"], "planting_wait_name", {"plant_type": plant_type})
            return BotResponse(
                chat_id,
                "Введите понятное название.\n\nНапример: Клубника, Помидоры, Розы у беседки.",
                keyboards.cancel_inline(),
            )
        if data.startswith("planting:date:"):
            option = data.rsplit(":", 1)[1]
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "planting_wait_date":
                return BotResponse(chat_id, "Диалог создания насаждения не найден.", keyboards.main_menu())
            payload = dict(dialog_state["payload"])
            if option == "custom":
                return BotResponse(
                    chat_id,
                    "Введите дату или месяц посадки.\n\nПодойдут варианты: май, май 2026, 05.2026, 2026-05, 25.05.2026.",
                    keyboards.cancel_inline(),
                )
            payload["planted_on"] = _planting_date_from_option(option, user["timezone"])
            return self._planting_location_step(conn, user, chat_id, payload)
        if data.startswith("planting:loc:"):
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "planting_wait_location":
                return BotResponse(chat_id, "Диалог создания насаждения не найден.", keyboards.main_menu())
            payload = dialog_state["payload"]
            location_raw = data.split(":")[2:]
            plot_id = None
            zone_id = None
            if location_raw[0] == "p":
                plot_id = int(location_raw[1])
            elif location_raw[0] == "z":
                zone_id = int(location_raw[1])
                zone = garden.get_zone(user["id"], zone_id)
                plot_id = zone["plot_id"] if zone else None
            elif location_raw[0] != "none":
                return BotResponse(chat_id, "Не удалось выбрать место насаждения.", keyboards.main_menu())
            planting_id = garden.add_planting(
                user["id"],
                payload["name"],
                variety=payload.get("variety"),
                planted_on=payload.get("planted_on"),
                plot_id=plot_id,
                zone_id=zone_id,
                plant_type=payload.get("plant_type", "plant"),
            )
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Насаждение #{planting_id} добавлено.", keyboards.main_menu())
        if data.startswith("planting:zone:"):
            dialog_state = dialog.get(user["id"])
            if not dialog_state or dialog_state["state"] != "planting_wait_zone":
                return BotResponse(chat_id, "Диалог создания насаждения не найден.", keyboards.main_menu())
            zone_raw = data.rsplit(":", 1)[1]
            zone_id = None if zone_raw == "none" else int(zone_raw)
            payload = dialog_state["payload"]
            planting_id = garden.add_planting(
                user["id"],
                payload["name"],
                variety=payload.get("variety"),
                planted_on=payload.get("planted_on"),
                plot_id=None,
                zone_id=zone_id,
                plant_type=payload.get("plant_type", "plant"),
            )
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Насаждение #{planting_id} добавлено.", keyboards.main_menu())
        if data == "settings:notify:toggle":
            current = user_service.settings_for(user["id"])
            enabled = not bool(current["notifications_enabled"])
            user_service.update_settings(user["id"], notifications_enabled=enabled)
            return self._settings_response(
                conn, user_service, user, chat_id, edit_message_id=message_id
            )
        if data.startswith("logtype:"):
            work_type = data.rsplit(":", 1)[1]
            dialog.set(user["id"], "log_wait_note", {"work_type": work_type})
            return BotResponse(chat_id, "Введите текст записи журнала.", keyboards.cancel_inline())
        if data == "log:add":
            dialog.set(user["id"], "log_wait_type", {})
            return BotResponse(chat_id, "Выберите тип работы.", keyboards.work_type_menu())
        if data.startswith("ref:plot_tasks:"):
            plot_id = int(data.rsplit(":", 1)[1])
            plot = garden.get_plot(user["id"], plot_id)
            if plot is None:
                return BotResponse(chat_id, "Участок не найден.", keyboards.garden_menu())
            return BotResponse(
                chat_id,
                messages.location_task_ideas(plot["name"]),
                keyboards.location_task_ideas_menu("plot", plot_id),
                message_id,
            )
        if data.startswith("ref:zone_tasks:"):
            zone_id = int(data.rsplit(":", 1)[1])
            zone = garden.get_zone(user["id"], zone_id)
            if zone is None:
                return BotResponse(chat_id, "Зона не найдена.", keyboards.garden_menu())
            return BotResponse(
                chat_id,
                messages.location_task_ideas(zone["name"]),
                keyboards.location_task_ideas_menu("zone", zone_id),
                message_id,
            )
        if data.startswith("ref:planting_tasks:"):
            planting_id = int(data.rsplit(":", 1)[1])
            planting = garden.get_planting(user["id"], planting_id)
            if planting is None:
                return BotResponse(chat_id, "Насаждение не найдено.", keyboards.garden_menu())
            return BotResponse(
                chat_id,
                messages.location_task_ideas(planting["name"]),
                keyboards.location_task_ideas_menu("planting", planting_id),
                message_id,
            )
        if data.startswith("idea:"):
            try:
                return self._start_task_from_idea(conn, user, chat_id, data)
            except ValueError:
                return BotResponse(chat_id, "Не удалось создать задачу из подсказки.", keyboards.main_menu())
        if data.startswith("ref:"):
            topic = data.rsplit(":", 1)[1]
            return BotResponse(chat_id, messages.reference(topic), keyboards.reference_menu(), message_id)
        if data == "delete:confirm":
            PrivacyService(conn).delete_user_data(user["id"])
            return BotResponse(
                chat_id,
                "Ваши данные удалены.",
                keyboards.main_menu(),
                callback_text="Удалено",
            )
        if data == "settings:quiet":
            dialog.set(user["id"], "settings_wait_quiet_start", {})
            return BotResponse(chat_id, "Введите начало тихих часов в формате HH:MM.", keyboards.cancel_inline())
        if data.startswith("settings:remind:"):
            value = data.rsplit(":", 1)[1]
            if value == "custom":
                dialog.set(user["id"], "settings_wait_reminder", {})
                return BotResponse(
                    chat_id,
                    "Введите за сколько минут до срока напоминать.",
                    keyboards.cancel_inline(),
                )
            user_service.update_settings(user["id"], reminder_lead_minutes=int(value))
            return self._settings_response(
                conn, user_service, user, chat_id, edit_message_id=message_id
            )

        return BotResponse(chat_id, "Неизвестное действие.", keyboards.main_menu())

    def _handle_dialog_input(
        self, conn, user: dict, chat_id: int, text: str, state: dict
    ) -> BotResponse:
        dialog = DialogStateService(conn)
        garden = GardenService(conn)
        user_service = UserService(conn, self.settings)
        state_name = state["state"]
        payload = dict(state["payload"])

        if state_name == "task_wait_title":
            if not text:
                return BotResponse(chat_id, "Введите непустое название задачи.", keyboards.cancel_inline())
            dialog.set(user["id"], "task_wait_due_at", {"title": text})
            return BotResponse(
                chat_id,
                "Когда нужно сделать задачу?\n\nМожно выбрать кнопку или написать дату: завтра 9:00, 25.05 12:00, 2026-05-25 12:00.",
                keyboards.task_due_menu(),
            )
        if state_name == "task_wait_due_at":
            try:
                due_at = iso(parse_local_datetime(text, user["timezone"]))
            except ValueError:
                return BotResponse(
                    chat_id,
                    "Не удалось разобрать дату.\n\nПопробуйте так: завтра 9:00, 25.05 12:00 или 2026-05-25 12:00.",
                    keyboards.task_due_menu(),
                )
            payload["due_at"] = due_at
            dialog.set(user["id"], "task_wait_repeat", payload)
            return BotResponse(chat_id, "Нужен повтор?", keyboards.repeat_menu())
        if state_name == "task_wait_description":
            payload["description"] = None if text == "-" else text
            return self._task_location_step(conn, user, chat_id, payload)
        if state_name == "task_edit_title":
            try:
                TaskService(conn).update_title(user["id"], int(payload["task_id"]), text)
            except ValueError:
                return BotResponse(chat_id, "Введите непустое название задачи.", keyboards.cancel_inline())
            dialog.clear(user["id"])
            task = TaskService(conn).get_task(user["id"], int(payload["task_id"]))
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]) if task else "Название обновлено.",
                keyboards.task_details(int(payload["task_id"])),
            )
        if state_name == "task_edit_due_at":
            try:
                due_at = iso(parse_local_datetime(text, user["timezone"]))
            except ValueError:
                return BotResponse(
                    chat_id,
                    "Не удалось разобрать дату.\n\nПопробуйте так: завтра 9:00, 25.05 12:00 или 2026-05-25 12:00.",
                    keyboards.task_due_menu(),
                )
            TaskService(conn).update_due_at(user["id"], int(payload["task_id"]), due_at)
            dialog.clear(user["id"])
            task = TaskService(conn).get_task(user["id"], int(payload["task_id"]))
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]) if task else "Дата задачи обновлена.",
                keyboards.task_details(int(payload["task_id"])),
            )
        if state_name == "task_edit_description":
            description = None if text == "-" else text
            TaskService(conn).update_description(user["id"], int(payload["task_id"]), description)
            dialog.clear(user["id"])
            task = TaskService(conn).get_task(user["id"], int(payload["task_id"]))
            return BotResponse(
                chat_id,
                messages.task_card(task, user["timezone"]) if task else "Описание обновлено.",
                keyboards.task_details(int(payload["task_id"])),
            )
        if state_name == "task_wait_snooze_at":
            try:
                due_at = iso(parse_local_datetime(text, user["timezone"]))
            except ValueError:
                return BotResponse(chat_id, "Не удалось разобрать дату.", keyboards.cancel_inline())
            TaskService(conn).snooze_task_until(user["id"], int(payload["task_id"]), due_at)
            dialog.clear(user["id"])
            return BotResponse(
                chat_id,
                f"Задача отложена до {format_local_datetime(due_at, user['timezone'])}.",
                keyboards.main_menu(),
            )
        if state_name == "task_wait_skip_reason":
            next_id = TaskService(conn).skip_task(user["id"], int(payload["task_id"]), text)
            dialog.clear(user["id"])
            result = "Задача пропущена."
            if next_id:
                result += f" Создан следующий повтор #{next_id}."
            return BotResponse(chat_id, result, keyboards.main_menu())
        if state_name == "log_wait_type":
            return BotResponse(chat_id, "Выберите тип работы кнопкой ниже.", keyboards.work_type_menu())
        if state_name == "log_wait_note":
            entry_id = JournalService(conn).create_entry(
                user["id"], text, work_type=payload.get("work_type", "other")
            )
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Запись журнала #{entry_id} добавлена.", keyboards.main_menu())
        if state_name == "work_wait_note":
            entry_id = JournalService(conn).create_entry(
                user["id"], text, work_type=payload.get("work_type", "other")
            )
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Запись журнала #{entry_id} добавлена.", keyboards.main_menu())
        if state_name == "work_wait_wait_until":
            wait_until = None
            if text != "-":
                try:
                    wait_until = parse_wait_until(text, user["timezone"])
                except ValueError:
                    return BotResponse(
                        chat_id,
                        "Не удалось разобрать срок ожидания. Введите дату или число дней.",
                        keyboards.cancel_inline(),
                    )
            payload["wait_until_date"] = wait_until
            dialog.set(user["id"], "work_wait_note", payload)
            return BotResponse(chat_id, "Введите заметку для обработки.", keyboards.cancel_inline())
        if state_name == "plot_wait_name":
            if not text:
                return BotResponse(chat_id, "Введите название участка.", keyboards.cancel_inline())
            plot_id = garden.add_plot(user["id"], text)
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Участок #{plot_id} добавлен.", keyboards.main_menu())
        if state_name == "plot_edit_name":
            try:
                garden.rename_plot(user["id"], int(payload["plot_id"]), text)
            except ValueError:
                return BotResponse(chat_id, "Введите непустое название участка.", keyboards.cancel_inline())
            dialog.clear(user["id"])
            plot = garden.get_plot(user["id"], int(payload["plot_id"]))
            return BotResponse(
                chat_id,
                messages.plot_card(plot, garden.list_zones(user["id"])) if plot else "Участок обновлен.",
                keyboards.plot_details(int(payload["plot_id"])),
            )
        if state_name == "zone_wait_name":
            if not text:
                return BotResponse(chat_id, "Введите название зоны.", keyboards.cancel_inline())
            plots = garden.list_plots(user["id"])
            if not plots:
                zone_id = garden.add_zone(user["id"], text)
                dialog.clear(user["id"])
                return BotResponse(chat_id, f"Зона #{zone_id} добавлена.", keyboards.main_menu())
            dialog.set(user["id"], "zone_wait_plot", {"name": text})
            return BotResponse(chat_id, "Выберите участок для зоны.", keyboards.choose_plot(plots))
        if state_name == "zone_edit_name":
            zone = garden.get_zone(user["id"], int(payload["zone_id"]))
            if zone is None:
                dialog.clear(user["id"])
                return BotResponse(chat_id, "Зона не найдена.", keyboards.garden_menu())
            try:
                garden.rename_zone(user["id"], int(payload["zone_id"]), text, zone["plot_id"])
            except ValueError:
                return BotResponse(chat_id, "Введите непустое название зоны.", keyboards.cancel_inline())
            dialog.clear(user["id"])
            updated = garden.get_zone(user["id"], int(payload["zone_id"]))
            return BotResponse(
                chat_id,
                messages.zone_card(updated) if updated else "Зона обновлена.",
                keyboards.zone_details(int(payload["zone_id"])),
            )
        if state_name == "planting_wait_name":
            if not text:
                return BotResponse(chat_id, "Введите понятное название насаждения.", keyboards.cancel_inline())
            payload["name"] = text
            dialog.set(user["id"], "planting_wait_date", payload)
            return BotResponse(
                chat_id,
                "Когда посадили?\n\nМожно выбрать кнопку или написать месяц/дату: май, май 2026, 05.2026, 2026-05, 25.05.2026. Если не помните, нажмите «Не знаю».",
                keyboards.planting_date_menu(),
            )
        if state_name == "planting_wait_variety":
            payload["variety"] = None if text == "-" else text
            dialog.set(user["id"], "planting_wait_date", payload)
            return BotResponse(
                chat_id,
                "Когда посадили?\n\nМожно выбрать кнопку или написать месяц/дату: май, май 2026, 05.2026, 2026-05, 25.05.2026. Если не помните, нажмите «Не знаю».",
                keyboards.planting_date_menu(),
            )
        if state_name == "planting_wait_date":
            try:
                payload["planted_on"] = parse_planting_date(text, user["timezone"])
            except ValueError:
                return BotResponse(
                    chat_id,
                    "Не удалось понять дату посадки.\n\nНапишите месяц или дату: май, май 2026, 05.2026, 2026-05, 25.05.2026. Можно отправить '-' если дата неизвестна.",
                    keyboards.planting_date_menu(),
                )
            return self._planting_location_step(conn, user, chat_id, payload)
        if state_name == "settings_wait_quiet_start":
            if not _valid_time(text):
                return BotResponse(chat_id, "Введите время в формате HH:MM.", keyboards.cancel_inline())
            dialog.set(user["id"], "settings_wait_quiet_end", {"quiet_start": text})
            return BotResponse(chat_id, "Введите окончание тихих часов в формате HH:MM.", keyboards.cancel_inline())
        if state_name == "settings_wait_quiet_end":
            if not _valid_time(text):
                return BotResponse(chat_id, "Введите время в формате HH:MM.", keyboards.cancel_inline())
            user_service.update_settings(
                user["id"], quiet_start=payload["quiet_start"], quiet_end=text
            )
            dialog.clear(user["id"])
            return self._settings_response(conn, user_service, user, chat_id)
        if state_name == "settings_wait_reminder":
            try:
                minutes = int(text)
            except ValueError:
                return BotResponse(chat_id, "Введите целое число минут.", keyboards.cancel_inline())
            if minutes <= 0:
                return BotResponse(chat_id, "Введите число больше нуля.", keyboards.cancel_inline())
            user_service.update_settings(user["id"], reminder_lead_minutes=minutes)
            dialog.clear(user["id"])
            return self._settings_response(conn, user_service, user, chat_id)

        dialog.clear(user["id"])
        return BotResponse(chat_id, "Диалог сброшен.", keyboards.main_menu())

    def _tasks_response(
        self, conn, user_id: int, chat_id: int, edit_message_id: int | None = None
    ) -> BotResponse:
        tasks = TaskService(conn).list_open(user_id)
        user = conn.execute("SELECT timezone FROM users WHERE id = ?", (user_id,)).fetchone()
        timezone_name = user["timezone"] if user else self.settings.default_timezone
        return BotResponse(
            chat_id,
            messages.tasks_list(tasks, timezone_name),
            keyboards.tasks_menu(tasks),
            edit_message_id,
        )

    def _start_task_dialog(self, conn, user_id: int, chat_id: int) -> BotResponse:
        DialogStateService(conn).set(user_id, "task_wait_title", {})
        return BotResponse(
            chat_id,
            "Новая задача\n\nНапишите короткое название. Например: Полить теплицу.",
            keyboards.cancel_inline(),
        )

    def _start_task_from_idea(self, conn, user: dict, chat_id: int, data: str) -> BotResponse:
        _, kind, raw_id, code = data.split(":", 3)
        garden = GardenService(conn)
        title = messages.task_idea_title(code)
        payload = {
            "title": title,
            "location_locked": True,
        }
        if kind == "p":
            plot = garden.get_plot(user["id"], int(raw_id))
            if plot is None:
                raise ValueError("plot not found")
            payload.update(
                {
                    "plot_id": plot["id"],
                    "zone_id": None,
                    "location_label": plot["name"],
                }
            )
        elif kind == "z":
            zone = garden.get_zone(user["id"], int(raw_id))
            if zone is None:
                raise ValueError("zone not found")
            payload.update(
                {
                    "plot_id": zone["plot_id"],
                    "zone_id": zone["id"],
                    "location_label": (
                        f"{zone['plot_name']} / {zone['name']}"
                        if zone.get("plot_name")
                        else zone["name"]
                    ),
                }
            )
        elif kind == "pl":
            planting = garden.get_planting(user["id"], int(raw_id))
            if planting is None:
                raise ValueError("planting not found")
            payload.update(
                {
                    "plot_id": planting["plot_id"],
                    "zone_id": planting["zone_id"],
                    "planting_id": planting["id"],
                    "location_label": messages.planting_location_label(planting),
                }
            )
        else:
            raise ValueError("unknown idea location")
        DialogStateService(conn).set(user["id"], "task_wait_due_at", payload)
        return BotResponse(
            chat_id,
            f"Задача: {title}\nМесто: {payload['location_label']}\n\nКогда нужно сделать?",
            keyboards.task_due_menu(),
            callback_text="Выберите срок",
        )

    def _task_location_step(self, conn, user: dict, chat_id: int, payload: dict) -> BotResponse:
        if payload.get("location_locked"):
            DialogStateService(conn).set(user["id"], "task_wait_confirm", payload)
            return BotResponse(
                chat_id,
                messages.task_confirmation(payload, user["timezone"]),
                keyboards.task_confirm(),
            )
        garden = GardenService(conn)
        zones = garden.list_zones(user["id"])
        plots = garden.list_plots(user["id"])
        plantings = garden.list_plantings(user["id"])
        if not zones and not plots and not plantings:
            payload["plot_id"] = None
            payload["zone_id"] = None
            payload["planting_id"] = None
            payload["location_label"] = "без привязки"
            DialogStateService(conn).set(user["id"], "task_wait_confirm", payload)
            return BotResponse(
                chat_id,
                messages.task_confirmation(payload, user["timezone"]),
                keyboards.task_confirm(),
            )
        DialogStateService(conn).set(user["id"], "task_wait_location", payload)
        return BotResponse(
            chat_id,
            "Где нужно выполнить задачу?\n\nВыберите насаждение, зону или участок. Можно оставить без привязки.",
            keyboards.task_location_menu_with_plantings(zones, plots, plantings),
        )

    def _planting_location_step(self, conn, user: dict, chat_id: int, payload: dict) -> BotResponse:
        dialog = DialogStateService(conn)
        garden = GardenService(conn)
        zones = garden.list_zones(user["id"])
        plots = garden.list_plots(user["id"])
        if not zones and not plots:
            planting_id = garden.add_planting(
                user["id"],
                payload["name"],
                variety=payload.get("variety"),
                planted_on=payload.get("planted_on"),
                plant_type=payload.get("plant_type", "plant"),
            )
            dialog.clear(user["id"])
            return BotResponse(chat_id, f"Насаждение #{planting_id} добавлено.", keyboards.main_menu())
        dialog.set(user["id"], "planting_wait_location", payload)
        return BotResponse(
            chat_id,
            "Выберите участок или зону для насаждения.",
            keyboards.choose_planting_location(zones, plots),
        )

    def _parse_location_callback(
        self, conn, user_id: int, parts: list[str]
    ) -> tuple[int | None, int | None, int | None]:
        garden = GardenService(conn)
        if parts[0] == "none":
            return None, None, None
        if parts[0] == "p":
            plot_id = int(parts[1])
            if garden.get_plot(user_id, plot_id) is None:
                raise ValueError("plot not found")
            return plot_id, None, None
        if parts[0] == "z":
            zone_id = int(parts[1])
            zone = garden.get_zone(user_id, zone_id)
            if zone is None:
                raise ValueError("zone not found")
            return zone["plot_id"], zone_id, None
        if parts[0] == "pl":
            planting_id = int(parts[1])
            planting = garden.get_planting(user_id, planting_id)
            if planting is None:
                raise ValueError("planting not found")
            return planting["plot_id"], planting["zone_id"], planting_id
        raise ValueError("unknown location")

    def _apply_location_payload(self, conn, user_id: int, payload: dict, data: str) -> None:
        parts = data.split(":")[2:]
        plot_id, zone_id, planting_id = self._parse_location_callback(conn, user_id, parts)
        garden = GardenService(conn)
        payload["plot_id"] = plot_id
        payload["zone_id"] = zone_id
        payload["planting_id"] = planting_id
        if planting_id is not None:
            planting = garden.get_planting(user_id, planting_id)
            payload["location_label"] = (
                messages.planting_location_label(planting) if planting else "без привязки"
            )
        elif zone_id is not None:
            zone = garden.get_zone(user_id, zone_id)
            payload["location_label"] = (
                f"{zone['plot_name']} / {zone['name']}" if zone and zone.get("plot_name") else zone["name"]
            )
        elif plot_id is not None:
            plot = garden.get_plot(user_id, plot_id)
            payload["location_label"] = plot["name"] if plot else "без привязки"
        else:
            payload["location_label"] = "без привязки"

    def _today_response(
        self, conn, user: dict, chat_id: int, edit_message_id: int | None = None
    ) -> BotResponse:
        data = TaskService(conn).today(user["id"], user["timezone"])
        tasks = data["overdue"] + data["today"] + data["upcoming"]
        return BotResponse(
            chat_id,
            messages.today(data, user["timezone"]),
            keyboards.today_menu(tasks),
            edit_message_id,
        )

    def _journal_response(
        self, conn, user_id: int, chat_id: int, edit_message_id: int | None = None
    ) -> BotResponse:
        rows = TaskService(conn).journal.list_recent(user_id)
        return BotResponse(chat_id, messages.journal(rows), keyboards.journal_menu(), edit_message_id)

    def _settings_response(
        self,
        conn,
        user_service: UserService,
        user: dict,
        chat_id: int,
        edit_message_id: int | None = None,
    ) -> BotResponse:
        settings = user_service.settings_for(user["id"])
        return BotResponse(
            chat_id,
            messages.settings(settings, user["timezone"]),
            keyboards.settings_menu(bool(settings["notifications_enabled"])),
            edit_message_id,
        )

    def _create_task(self, conn, user: dict, payload: str) -> str:
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 2:
            return "Формат: /task YYYY-MM-DD HH:MM | название | repeat=weekly"
        due_at = iso(parse_local_datetime(parts[0], user["timezone"]))
        title = parts[1]
        repeat = "none"
        for part in parts[2:]:
            if part.startswith("repeat="):
                repeat = part.split("=", 1)[1].strip()
        service = TaskService(conn)
        remind_at = service.default_remind_at(user["id"], due_at)
        task_id = service.create_task(
            user_id=user["id"],
            title=title,
            due_at=due_at,
            repeat_rule=repeat,
            remind_at=remind_at,
        )
        return f"Задача #{task_id} «{title}» создана"

    def _quick_work_log(
        self, conn, user: dict, chat_id: int, work_type: str, payload: str
    ) -> BotResponse:
        wait_until = None
        note = payload.strip()
        if work_type == "treatment":
            parts = [part for part in note.split() if part.startswith("wait=")]
            for part in parts:
                wait_until = parse_wait_until(part.split("=", 1)[1], user["timezone"])
                note = note.replace(part, "").strip()
        entry_id = JournalService(conn).create_entry(
            user["id"],
            note or WORK_TYPE_TITLES.get(work_type, "Работа"),
            work_type=work_type,
            wait_until_date=wait_until,
        )
        return BotResponse(chat_id, f"Запись журнала #{entry_id} добавлена.")

    def _list_tasks(self, conn, user_id: int) -> str:
        tasks = TaskService(conn).list_open(user_id)
        if not tasks:
            return "Открытых задач нет"
        user = conn.execute("SELECT timezone FROM users WHERE id = ?", (user_id,)).fetchone()
        timezone_name = user["timezone"] if user else self.settings.default_timezone
        lines = ["Открытые задачи:"]
        for task in tasks:
            due = format_local_datetime(task["due_at"], timezone_name)
            repeat = "" if task["repeat_rule"] == "none" else f", {task['repeat_rule']}"
            lines.append(f"#{task['id']} {due} - {task['title']}{repeat}")
        return "\n".join(lines)

    def _done_task(self, conn, user_id: int, raw_id: str) -> str:
        try:
            task_id = int(raw_id.strip())
            next_id = TaskService(conn).complete_task(user_id, task_id)
        except ValueError as exc:
            return str(exc)
        if next_id:
            return f"Задача #{task_id} закрыта, создан повтор #{next_id}"
        return f"Задача #{task_id} закрыта"

    def _create_planting(self, conn, user: dict, payload: str) -> str:
        parts = [part.strip() for part in payload.split("|")]
        name = parts[0]
        variety = None
        planted_on = None
        if len(parts) == 2:
            try:
                planted_on = parse_planting_date(parts[1], user["timezone"])
            except ValueError:
                variety = parts[1] if parts[1] else None
        else:
            variety = parts[1] if len(parts) > 1 and parts[1] else None
            if len(parts) > 2 and parts[2]:
                try:
                    planted_on = parse_planting_date(parts[2], user["timezone"])
                except ValueError:
                    return "Не удалось понять дату посадки. Используйте: май, май 2026, 05.2026 или 2026-05-25."
        planting_id = GardenService(conn).add_planting(
            user["id"], name=name, variety=variety, planted_on=planted_on, plant_type="plant"
        )
        return f"Насаждение #{planting_id} добавлено"

    def _journal(self, conn, user_id: int) -> str:
        rows = TaskService(conn).journal.list_recent(user_id)
        if not rows:
            return "Журнал пуст"
        return "\n".join(
            ["Журнал:"] + [f"#{row['id']} {row['created_at']} - {row['note']}" for row in rows]
        )

    def _settings(self, user_service: UserService, user_id: int, payload: str) -> str:
        parts = payload.split()
        if parts[:1] == ["quiet"] and len(parts) == 3:
            user_service.update_settings(user_id, quiet_start=parts[1], quiet_end=parts[2])
            return "Quiet hours обновлены"
        if parts[:1] == ["notify"] and len(parts) == 2:
            enabled = parts[1].lower() in {"on", "1", "true", "yes"}
            user_service.update_settings(user_id, notifications_enabled=enabled)
            return "Уведомления включены" if enabled else "Уведомления выключены"
        settings = user_service.settings_for(user_id)
        return (
            f"Quiet hours: {settings['quiet_start']}-{settings['quiet_end']}\n"
            f"Напоминание за {settings['reminder_lead_minutes']} мин."
        )

    def _diag(self, conn) -> str:
        data = DiagnosticsService(conn, self.settings.database_path).collect()
        return "\n".join(f"{key}: {value}" for key, value in data.items())

    @staticmethod
    def _format_items(rows: list[dict], title: str) -> str:
        if not rows:
            return f"{title}: пусто"
        return "\n".join([f"{title}:"] + [f"#{row['id']} {row['name']}" for row in rows])


def _due_at_from_option(option: str, timezone_name: str) -> str | None:
    if option == "none":
        return None
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz).replace(second=0, microsecond=0)
    if option == "today_evening":
        target = datetime.combine(now.date(), dt_time(18, 0), tzinfo=tz)
        if target <= now:
            target = target + timedelta(days=1)
        return iso(target.astimezone(timezone.utc))
    if option == "tomorrow_morning":
        target = datetime.combine(now.date() + timedelta(days=1), dt_time(9, 0), tzinfo=tz)
        return iso(target.astimezone(timezone.utc))
    if option == "tomorrow_evening":
        target = datetime.combine(now.date() + timedelta(days=1), dt_time(18, 0), tzinfo=tz)
        return iso(target.astimezone(timezone.utc))
    raise ValueError("unsupported due option")


def _planting_date_from_option(option: str, timezone_name: str) -> str | None:
    if option == "unknown":
        return None
    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    year = now.year
    month = now.month
    if option == "last_month":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    elif option != "this_month":
        raise ValueError("unsupported planting date option")
    return format_month(year, month)


def _valid_time(value: str) -> bool:
    if not TIME_RE.match(value):
        return False
    hour, minute = value.split(":", 1)
    return 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59


def _dispatch_response(api: TelegramApi, response: BotResponse) -> None:
    if response.answer_callback_query_id:
        api.answer_callback_query(response.answer_callback_query_id, response.callback_text)
    if response.edit_message_id is not None:
        try:
            api.edit_message_text(
                response.chat_id,
                response.edit_message_id,
                response.text,
                reply_markup=response.reply_markup,
            )
        except Exception:
            logger.exception("failed to edit message, falling back to send_message")
            api.send_message(response.chat_id, response.text, reply_markup=response.reply_markup)
    else:
        api.send_message(response.chat_id, response.text, reply_markup=response.reply_markup)


def run() -> None:
    settings = Settings.from_env()
    settings.require_bot_token()
    configure_logging(settings.log_level)
    StartupBackupService(settings).maybe_backup()
    apply_migrations(settings.database_path)
    api = TelegramApi(settings.bot_token, timeout=settings.poll_timeout_seconds + 5)
    app = BotApplication(settings, api)
    with connect(settings.database_path) as conn:
        result = StartupNotificationService(conn, settings, api).send_once_for_version()
        if result["enabled"]:
            logger.info("startup update notification result=%s", result)
    offset: int | None = None
    logger.info("bot polling started")
    while True:
        try:
            updates = api.get_updates(offset=offset, timeout=settings.poll_timeout_seconds)
            for update in updates:
                offset = int(update["update_id"]) + 1
                callback = parse_callback(update)
                if callback is not None:
                    _dispatch_response(api, app.handle_callback(callback))
                    continue
                message = parse_message(update)
                if message is not None:
                    _dispatch_response(api, app.handle_message(message))
        except Exception:
            logger.exception("bot polling iteration failed")
            time.sleep(5)


if __name__ == "__main__":
    run()
