from __future__ import annotations

import sqlite3

from ogorodom_bot.repositories.garden import GardenRepository
from ogorodom_bot.repositories.tasks import JournalRepository


class GardenService:
    def __init__(self, conn: sqlite3.Connection):
        self.repo = GardenRepository(conn)
        self.journal = JournalRepository(conn)

    def add_plot(self, user_id: int, name: str, notes: str | None = None) -> int:
        plot_id = self.repo.create_plot(user_id, name, notes)
        self.journal.create(user_id, "plot_created", f"Создан участок: {name}", "plot", plot_id)
        return plot_id

    def list_plots(self, user_id: int) -> list[dict]:
        return self.repo.list_plots(user_id)

    def add_zone(
        self, user_id: int, name: str, plot_id: int | None = None, notes: str | None = None
    ) -> int:
        zone_id = self.repo.create_zone(user_id, name, plot_id, notes)
        self.journal.create(user_id, "zone_created", f"Создана зона: {name}", "zone", zone_id)
        return zone_id

    def list_zones(self, user_id: int) -> list[dict]:
        return self.repo.list_zones(user_id)

    def add_planting(
        self,
        user_id: int,
        name: str,
        variety: str | None = None,
        zone_id: int | None = None,
        planted_on: str | None = None,
        notes: str | None = None,
    ) -> int:
        planting_id = self.repo.create_planting(
            user_id, name, variety=variety, zone_id=zone_id, planted_on=planted_on, notes=notes
        )
        self.journal.create(
            user_id, "planting_created", f"Добавлена посадка: {name}", "planting", planting_id
        )
        return planting_id

    def list_plantings(self, user_id: int) -> list[dict]:
        return self.repo.list_plantings(user_id)
