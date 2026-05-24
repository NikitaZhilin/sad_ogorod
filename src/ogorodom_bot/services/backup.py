from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class BackupService:
    def __init__(self, conn: sqlite3.Connection, database_path: Path, backup_dir: Path):
        self.conn = conn
        self.database_path = database_path
        self.backup_dir = backup_dir

    def create_backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.backup_dir / f"ogorodom-{stamp}.sqlite3"
        self.conn.commit()
        with closing(sqlite3.connect(target)) as backup_conn:
            self.conn.backup(backup_conn)
        size = target.stat().st_size
        self.conn.execute(
            "INSERT INTO backups(path, size_bytes) VALUES (?, ?)", (str(target), size)
        )
        return target

    def restore_backup(self, source: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(source)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, self.database_path)
