from __future__ import annotations

import argparse
from pathlib import Path

from ogorodom_bot.config import Settings
from ogorodom_bot.db.connection import connect
from ogorodom_bot.db.migrations import apply_migrations
from ogorodom_bot.services.backup import BackupService
from ogorodom_bot.services.diagnostics import DiagnosticsService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "backup", "diag", "restore"])
    parser.add_argument("--source", help="backup path for restore")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.command == "migrate":
        versions = apply_migrations(settings.database_path)
        print("Applied: " + ", ".join(versions) if versions else "No migrations")
        return

    apply_migrations(settings.database_path)
    with connect(settings.database_path) as conn:
        if args.command == "backup":
            print(BackupService(conn, settings.database_path, settings.backup_dir).create_backup())
        elif args.command == "diag":
            for key, value in DiagnosticsService(conn, settings.database_path).collect().items():
                print(f"{key}: {value}")
        elif args.command == "restore":
            if not args.source:
                raise SystemExit("--source is required")
            BackupService(conn, settings.database_path, settings.backup_dir).restore_backup(
                Path(args.source)
            )
            print("Restored")


if __name__ == "__main__":
    main()
