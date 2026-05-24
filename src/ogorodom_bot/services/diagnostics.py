from __future__ import annotations

import sqlite3
from pathlib import Path

from ogorodom_bot.db.migrations import current_version


class DiagnosticsService:
    def __init__(self, conn: sqlite3.Connection, database_path: Path):
        self.conn = conn
        self.database_path = database_path

    def collect(self) -> dict:
        return {
            "database_path": str(self.database_path),
            "database_exists": self.database_path.exists(),
            "database_size_bytes": self.database_path.stat().st_size
            if self.database_path.exists()
            else 0,
            "migration_version": current_version(self.database_path),
            "users": self._count("users"),
            "open_tasks": self._count("tasks", "status IN ('open', 'active', 'snoozed')"),
            "pending_reminders": self._count("reminder_events", "status = 'pending'"),
            "journal_entries": self._count("journal_entries"),
        }

    def _count(self, table: str, where: str | None = None) -> int:
        sql = f"SELECT COUNT(*) AS total FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.conn.execute(sql).fetchone()
        return int(row["total"])
