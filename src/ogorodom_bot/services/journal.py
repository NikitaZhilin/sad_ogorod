from __future__ import annotations

import sqlite3

from ogorodom_bot.repositories.tasks import JournalRepository


WORK_TYPE_TITLES = {
    "watering": "Полив",
    "mowing": "Покос",
    "treatment": "Обработка",
    "weeding": "Прополка",
    "fertilizing": "Подкормка",
    "planting": "Посадка",
    "harvesting": "Сбор урожая",
    "other": "Другое",
}


class JournalService:
    def __init__(self, conn: sqlite3.Connection):
        self.repo = JournalRepository(conn)

    def create_entry(
        self,
        user_id: int,
        note: str,
        work_type: str = "other",
        task_id: int | None = None,
        zone_id: int | None = None,
        planting_id: int | None = None,
        wait_until_date: str | None = None,
    ) -> int:
        title = WORK_TYPE_TITLES.get(work_type, work_type)
        return self.repo.create(
            user_id=user_id,
            entry_type="work_log",
            note=note.strip() or title,
            entity_type="work",
            entity_id=None,
            work_type=work_type,
            task_id=task_id,
            zone_id=zone_id,
            planting_id=planting_id,
            wait_until_date=wait_until_date,
        )

    def list_recent(self, user_id: int, limit: int = 10) -> list[dict]:
        return self.repo.list_recent(user_id, limit)
