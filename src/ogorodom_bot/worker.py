from __future__ import annotations

import logging
import time

from ogorodom_bot.config import Settings
from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.logging_config import configure_logging
from ogorodom_bot.repositories.tasks import ReminderRepository
from ogorodom_bot.services.tasks import TaskService
from ogorodom_bot.services.time_utils import iso, utc_now
from ogorodom_bot.telegram_api import TelegramApi

logger = logging.getLogger(__name__)


def tick(settings: Settings, api: TelegramApi) -> dict[str, int]:
    with connect(settings.database_path) as conn:
        scheduled = TaskService(conn).schedule_due_reminders(utc_now())
        reminders = ReminderRepository(conn)
        pending = reminders.list_pending(iso(utc_now()))
        sent = 0
        failed = 0
        for event in pending:
            text = f"Напоминание: {event['title']}"
            if event["due_at"]:
                text += f"\nСрок: {event['due_at']}"
            try:
                api.send_message(int(event["telegram_id"]), text)
            except Exception as exc:
                logger.exception("failed to send reminder event_id=%s", event["id"])
                reminders.mark_failed(event["id"], str(exc))
                failed += 1
            else:
                reminders.mark_sent(event["id"])
                sent += 1
        return {"scheduled": scheduled, "sent": sent, "failed": failed}


def run() -> None:
    settings = Settings.from_env()
    settings.require_bot_token()
    configure_logging(settings.log_level)
    apply_migrations(settings.database_path)
    api = TelegramApi(settings.bot_token)
    logger.info("worker started")
    while True:
        try:
            result = tick(settings, api)
            if any(result.values()):
                logger.info("worker tick result=%s", result)
        except Exception:
            logger.exception("worker tick failed")
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    run()
