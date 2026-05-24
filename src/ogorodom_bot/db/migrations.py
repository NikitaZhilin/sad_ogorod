from __future__ import annotations

import sqlite3
from pathlib import Path

from ogorodom_bot.db.connection import connect


MIGRATIONS: list[tuple[str, str]] = [
    (
        "0001_initial",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            full_name TEXT,
            timezone TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            quiet_start TEXT NOT NULL,
            quiet_end TEXT NOT NULL,
            reminder_lead_minutes INTEGER NOT NULL,
            notifications_enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plot_id INTEGER REFERENCES plots(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS plantings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            variety TEXT,
            planted_on TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            plot_id INTEGER REFERENCES plots(id) ON DELETE SET NULL,
            zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
            planting_id INTEGER REFERENCES plantings(id) ON DELETE SET NULL,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            repeat_rule TEXT NOT NULL DEFAULT 'none',
            remind_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_user_status_due
            ON tasks(user_id, status, due_at);

        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type TEXT,
            entity_id INTEGER,
            entry_type TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reminder_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            send_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_reminder_events_pending
            ON reminder_events(status, send_at);

        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "0002_dialog_states",
        """
        CREATE TABLE IF NOT EXISTS dialog_states (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            state TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        "0003_startup_broadcasts",
        """
        CREATE TABLE IF NOT EXISTS startup_broadcasts (
            version TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
]


def apply_migrations(database_path: Path | str) -> list[str]:
    applied: list[str] = []
    with connect(database_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        existing = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, sql in MIGRATIONS:
            if version in existing:
                continue
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            applied.append(version)
    return applied


def current_version(database_path: Path | str) -> str | None:
    try:
        with connect(database_path) as conn:
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY applied_at DESC, version DESC LIMIT 1"
            ).fetchone()
            return row["version"] if row else None
    except sqlite3.OperationalError:
        return None


if __name__ == "__main__":
    from ogorodom_bot.config import Settings

    settings = Settings.from_env()
    versions = apply_migrations(settings.database_path)
    if versions:
        print("Applied migrations: " + ", ".join(versions))
    else:
        print("No migrations to apply")
