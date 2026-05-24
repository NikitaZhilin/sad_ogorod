from __future__ import annotations

import tempfile
from pathlib import Path

from ogorodom_bot.config import Settings


def test_settings(db_path: Path, backup_dir: Path) -> Settings:
    return Settings(
        bot_token="test-token",
        app_env="test",
        database_path=db_path,
        backup_dir=backup_dir,
        log_level="CRITICAL",
        poll_timeout_seconds=1,
        worker_interval_seconds=1,
        default_timezone="Europe/Moscow",
        default_quiet_start="22:00",
        default_quiet_end="08:00",
        reminder_lead_minutes=60,
    )


class TempApp:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "ogorodom.sqlite3"
        self.backup_dir = self.root / "backups"
        self.settings = test_settings(self.db_path, self.backup_dir)

    def cleanup(self) -> None:
        self.tmp.cleanup()
