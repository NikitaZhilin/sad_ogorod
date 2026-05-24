from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class WorkTypeRepository(Repository):
    def list_all(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM work_types ORDER BY code").fetchall()
        return [dict(row) for row in rows]

    def get(self, code: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM work_types WHERE code = ?", (code,)).fetchone()
        return self._row_to_dict(row)
