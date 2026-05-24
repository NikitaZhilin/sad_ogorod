from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from ogorodom_bot.config import Settings
from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.logging_config import configure_logging
from ogorodom_bot.services.backup import BackupService
from ogorodom_bot.services.diagnostics import DiagnosticsService
from ogorodom_bot.services.garden import GardenService
from ogorodom_bot.services.tasks import TaskService
from ogorodom_bot.services.time_utils import iso, parse_local_datetime
from ogorodom_bot.services.users import UserService
from ogorodom_bot.telegram_api import TelegramApi

logger = logging.getLogger(__name__)


HELP = """Огородом:
/task YYYY-MM-DD HH:MM | название | repeat=none|daily|weekly|monthly|yearly
/tasks - открытые задачи
/done ID - закрыть задачу
/plot название - добавить участок
/plots - список участков
/zone название - добавить зону
/zones - список зон
/planting название | сорт | YYYY-MM-DD - добавить посадку
/plantings - список посадок
/journal - последние записи
/settings quiet 22:00 08:00
/settings notify on|off
/backup - сделать backup SQLite
/diag - диагностика"""


@dataclass
class IncomingMessage:
    update_id: int
    chat_id: int
    telegram_id: int
    full_name: str
    text: str


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


class BotApplication:
    def __init__(self, settings: Settings, api: TelegramApi):
        self.settings = settings
        self.api = api

    def handle(self, message: IncomingMessage) -> str:
        with connect(self.settings.database_path) as conn:
            user_service = UserService(conn, self.settings)
            user = user_service.ensure_user(message.telegram_id, message.full_name)
            text = message.text
            if text in {"/start", "/help"}:
                return HELP
            if text.startswith("/task "):
                return self._create_task(conn, user, text[len("/task ") :])
            if text == "/tasks":
                return self._list_tasks(conn, user["id"])
            if text.startswith("/done "):
                return self._done_task(conn, user["id"], text[len("/done ") :])
            if text.startswith("/plot "):
                service = GardenService(conn)
                plot_id = service.add_plot(user["id"], text[len("/plot ") :].strip())
                return f"Участок #{plot_id} добавлен"
            if text == "/plots":
                return self._format_items(GardenService(conn).list_plots(user["id"]), "Участки")
            if text.startswith("/zone "):
                service = GardenService(conn)
                zone_id = service.add_zone(user["id"], text[len("/zone ") :].strip())
                return f"Зона #{zone_id} добавлена"
            if text == "/zones":
                return self._format_items(GardenService(conn).list_zones(user["id"]), "Зоны")
            if text.startswith("/planting "):
                return self._create_planting(conn, user["id"], text[len("/planting ") :])
            if text == "/plantings":
                return self._format_items(
                    GardenService(conn).list_plantings(user["id"]), "Посадки"
                )
            if text == "/journal":
                return self._journal(conn, user["id"])
            if text.startswith("/settings "):
                return self._settings(user_service, user["id"], text[len("/settings ") :])
            if text == "/backup":
                path = BackupService(
                    conn, self.settings.database_path, self.settings.backup_dir
                ).create_backup()
                return f"Backup создан: {path.name}"
            if text == "/diag":
                return self._diag(conn)
            return "Неизвестная команда. /help"

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
        return f"Задача #{task_id} создана"

    def _list_tasks(self, conn, user_id: int) -> str:
        tasks = TaskService(conn).list_open(user_id)
        if not tasks:
            return "Открытых задач нет"
        lines = ["Открытые задачи:"]
        for task in tasks:
            due = task["due_at"] or "без срока"
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

    def _create_planting(self, conn, user_id: int, payload: str) -> str:
        parts = [part.strip() for part in payload.split("|")]
        name = parts[0]
        variety = parts[1] if len(parts) > 1 and parts[1] else None
        planted_on = parts[2] if len(parts) > 2 and parts[2] else None
        planting_id = GardenService(conn).add_planting(
            user_id, name=name, variety=variety, planted_on=planted_on
        )
        return f"Посадка #{planting_id} добавлена"

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


def run() -> None:
    settings = Settings.from_env()
    settings.require_bot_token()
    configure_logging(settings.log_level)
    apply_migrations(settings.database_path)
    api = TelegramApi(settings.bot_token, timeout=settings.poll_timeout_seconds + 5)
    app = BotApplication(settings, api)
    offset: int | None = None
    logger.info("bot polling started")
    while True:
        try:
            updates = api.get_updates(offset=offset, timeout=settings.poll_timeout_seconds)
            for update in updates:
                offset = int(update["update_id"]) + 1
                message = parse_message(update)
                if message is None:
                    continue
                response = app.handle(message)
                api.send_message(message.chat_id, response)
        except Exception:
            logger.exception("bot polling iteration failed")
            time.sleep(5)


if __name__ == "__main__":
    run()
