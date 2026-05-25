from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class GardenRepository(Repository):
    def create_plot(self, user_id: int, name: str, notes: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO plots(user_id, name, notes) VALUES (?, ?, ?)",
            (user_id, name, notes),
        )
        return int(cur.lastrowid)

    def list_plots(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM plots WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_plot(self, user_id: int, plot_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM plots WHERE user_id = ? AND id = ?", (user_id, plot_id)
        ).fetchone()
        return self._row_to_dict(row)

    def update_plot(self, user_id: int, plot_id: int, name: str) -> None:
        self.conn.execute(
            "UPDATE plots SET name = ? WHERE user_id = ? AND id = ?",
            (name, user_id, plot_id),
        )

    def delete_plot(self, user_id: int, plot_id: int) -> None:
        self.conn.execute("DELETE FROM plots WHERE user_id = ? AND id = ?", (user_id, plot_id))

    def create_zone(
        self, user_id: int, name: str, plot_id: int | None = None, notes: str | None = None
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO zones(user_id, plot_id, name, notes) VALUES (?, ?, ?, ?)",
            (user_id, plot_id, name, notes),
        )
        return int(cur.lastrowid)

    def list_zones(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT z.*, p.name AS plot_name
            FROM zones z
            LEFT JOIN plots p ON p.id = z.plot_id
            WHERE z.user_id = ?
            ORDER BY z.id
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_zone(self, user_id: int, zone_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT z.*, p.name AS plot_name
            FROM zones z
            LEFT JOIN plots p ON p.id = z.plot_id
            WHERE z.user_id = ? AND z.id = ?
            """,
            (user_id, zone_id),
        ).fetchone()
        return self._row_to_dict(row)

    def update_zone(self, user_id: int, zone_id: int, name: str, plot_id: int | None) -> None:
        self.conn.execute(
            "UPDATE zones SET name = ?, plot_id = ? WHERE user_id = ? AND id = ?",
            (name, plot_id, user_id, zone_id),
        )

    def delete_zone(self, user_id: int, zone_id: int) -> None:
        self.conn.execute("DELETE FROM zones WHERE user_id = ? AND id = ?", (user_id, zone_id))

    def create_planting(
        self,
        user_id: int,
        name: str,
        variety: str | None = None,
        zone_id: int | None = None,
        planted_on: str | None = None,
        notes: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO plantings(user_id, zone_id, name, variety, planted_on, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, zone_id, name, variety, planted_on, notes),
        )
        return int(cur.lastrowid)

    def list_plantings(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT pl.*, z.name AS zone_name
            FROM plantings pl
            LEFT JOIN zones z ON z.id = pl.zone_id
            WHERE pl.user_id = ?
            ORDER BY pl.id
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
