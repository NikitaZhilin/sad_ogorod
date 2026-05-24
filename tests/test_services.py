from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.repositories.tasks import ReminderRepository
from ogorodom_bot.services.backup import BackupService
from ogorodom_bot.services.garden import GardenService
from ogorodom_bot.services.tasks import TaskService
from ogorodom_bot.services.time_utils import iso, quiet_adjusted
from ogorodom_bot.services.users import UserService
from tests.helpers import TempApp


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TempApp()
        apply_migrations(self.app.db_path)

    def tearDown(self) -> None:
        self.app.cleanup()

    def test_user_garden_task_journal_flow(self) -> None:
        with connect(self.app.db_path) as conn:
            user = UserService(conn, self.app.settings).ensure_user(10, "Test User")
            garden = GardenService(conn)
            plot_id = garden.add_plot(user["id"], "Север")
            zone_id = garden.add_zone(user["id"], "Теплица", plot_id=plot_id)
            planting_id = garden.add_planting(
                user["id"], "Томат", variety="Черри", zone_id=zone_id
            )
            task_id = TaskService(conn).create_task(
                user["id"],
                "Полить",
                due_at="2026-05-25T09:00:00+00:00",
                repeat_rule="weekly",
                remind_at="2026-05-25T08:00:00+00:00",
                planting_id=planting_id,
            )
            next_id = TaskService(conn).complete_task(user["id"], task_id)
            open_tasks = TaskService(conn).list_open(user["id"])

        self.assertIsNotNone(next_id)
        self.assertEqual(open_tasks[0]["id"], next_id)
        self.assertEqual(open_tasks[0]["due_at"], "2026-06-01T09:00:00+00:00")

    def test_quiet_hours_move_reminder_to_morning(self) -> None:
        send_at = datetime(2026, 5, 25, 20, 30, tzinfo=timezone.utc)
        adjusted = quiet_adjusted(send_at, "22:00", "08:00", "Europe/Moscow")
        self.assertEqual(adjusted.isoformat(), "2026-05-26T05:00:00+00:00")

    def test_schedule_reminders_and_backup(self) -> None:
        with connect(self.app.db_path) as conn:
            user = UserService(conn, self.app.settings).ensure_user(10, "Test User")
            task_id = TaskService(conn).create_task(
                user["id"],
                "Внести удобрение",
                due_at="2026-05-25T10:00:00+00:00",
                remind_at="2026-05-25T08:00:00+00:00",
            )
            scheduled = TaskService(conn).schedule_due_reminders(
                datetime(2026, 5, 25, 8, 30, tzinfo=timezone.utc)
            )
            pending = ReminderRepository(conn).list_pending(
                iso(datetime(2026, 5, 25, 8, 30, tzinfo=timezone.utc))
            )
            backup_path = BackupService(
                conn, self.app.db_path, self.app.backup_dir
            ).create_backup()

        self.assertEqual(scheduled, 1)
        self.assertEqual(pending[0]["task_id"], task_id)
        self.assertTrue(backup_path.exists())


if __name__ == "__main__":
    unittest.main()
