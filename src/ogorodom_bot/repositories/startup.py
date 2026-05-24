from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class StartupBroadcastRepository(Repository):
    def get(self, version: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM startup_broadcasts WHERE version = ?", (version,)
        ).fetchone()
        return self._row_to_dict(row)

    def create(self, version: str, message: str, sent_count: int, failed_count: int) -> None:
        self.conn.execute(
            """
            INSERT INTO startup_broadcasts(version, message, sent_count, failed_count)
            VALUES (?, ?, ?, ?)
            """,
            (version, message, sent_count, failed_count),
        )
