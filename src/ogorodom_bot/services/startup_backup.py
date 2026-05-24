from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from ogorodom_bot.config import Settings

logger = logging.getLogger(__name__)


class StartupBackupService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def maybe_backup(self) -> Path | None:
        if not self.settings.startup_backup_enabled:
            return None
        source = self.settings.database_path
        if not source.exists():
            logger.info("startup backup skipped: database does not exist")
            return None
        backup_dir = self.settings.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        marker = backup_dir / ".startup-backup-last"
        lock = backup_dir / ".startup-backup.lock"
        now = int(time.time())
        if marker.exists():
            try:
                last = int(marker.read_text(encoding="utf-8").strip())
            except ValueError:
                last = 0
            if now - last < self.settings.startup_backup_min_interval_seconds:
                logger.info("startup backup skipped: throttled")
                return None
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            logger.info("startup backup skipped: another process is running backup")
            return None
        try:
            with os.fdopen(lock_fd, "w", encoding="utf-8") as handle:
                handle.write(str(now))
            if marker.exists():
                try:
                    last = int(marker.read_text(encoding="utf-8").strip())
                except ValueError:
                    last = 0
                if now - last < self.settings.startup_backup_min_interval_seconds:
                    logger.info("startup backup skipped: throttled")
                    return None
            target = backup_dir / f"startup-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now))}.sqlite3"
            with closing(sqlite3.connect(source)) as source_conn:
                with closing(sqlite3.connect(target)) as backup_conn:
                    source_conn.backup(backup_conn)
            marker.write_text(str(now), encoding="utf-8")
            logger.info("startup backup created path=%s size_bytes=%s", target, target.stat().st_size)
            return target
        finally:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
