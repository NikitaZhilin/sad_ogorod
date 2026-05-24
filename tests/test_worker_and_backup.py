from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.repositories.tasks import ReminderRepository
from ogorodom_bot.services.startup_backup import StartupBackupService
from ogorodom_bot.services.tasks import TaskService
from ogorodom_bot.services.time_utils import iso
from ogorodom_bot.services.users import UserService
from ogorodom_bot.worker import dry_run
from tests.helpers import TempApp


class WorkerAndBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TempApp()
        apply_migrations(self.app.db_path)

    def tearDown(self) -> None:
        self.app.cleanup()

    def test_startup_backup_is_throttled(self) -> None:
        service = StartupBackupService(self.app.settings)

        first = service.maybe_backup()
        second = service.maybe_backup()

        self.assertIsNotNone(first)
        self.assertTrue(first.exists())
        self.assertIsNone(second)

    def test_startup_backup_skips_when_locked(self) -> None:
        lock = self.app.settings.backup_dir / ".startup-backup.lock"
        self.app.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        lock.write_text("locked", encoding="utf-8")

        try:
            result = StartupBackupService(self.app.settings).maybe_backup()
        finally:
            lock.unlink(missing_ok=True)

        self.assertIsNone(result)

    def test_dry_run_reminders_does_not_mutate_pending_event(self) -> None:
        with connect(self.app.db_path) as conn:
            user = UserService(conn, self.app.settings).ensure_user(100, "User")
            task_id = TaskService(conn).create_task(
                user["id"],
                "Полить",
                due_at="2000-01-01T10:00:00+00:00",
                remind_at="2000-01-01T08:00:00+00:00",
            )
            ReminderRepository(conn).create(
                task_id,
                user["id"],
                iso(datetime(2000, 1, 1, 8, 0, tzinfo=timezone.utc)),
            )

        settings = replace(self.app.settings)
        rows = dry_run(settings)

        self.assertEqual(rows[0]["source"], "event")
        with connect(self.app.db_path) as conn:
            pending = ReminderRepository(conn).list_pending(
                iso(datetime(2026, 5, 25, 8, 30, tzinfo=timezone.utc))
            )
        self.assertEqual(pending[0]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
