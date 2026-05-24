from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    app_env: str
    app_version: str
    send_startup_update_on_boot: bool
    startup_update_message: str
    testing_notice_enabled: bool
    testing_notice_text: str
    database_path: Path
    backup_dir: Path
    log_level: str
    poll_timeout_seconds: int
    worker_interval_seconds: int
    startup_backup_enabled: bool
    startup_backup_min_interval_seconds: int
    default_timezone: str
    default_quiet_start: str
    default_quiet_end: str
    reminder_lead_minutes: int

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
            app_env=os.getenv("APP_ENV", "development"),
            app_version=os.getenv("APP_VERSION", "dev"),
            send_startup_update_on_boot=_bool_env("SEND_STARTUP_UPDATE_ON_BOOT", False),
            startup_update_message=os.getenv("STARTUP_UPDATE_MESSAGE", ""),
            testing_notice_enabled=_bool_env("TESTING_NOTICE_ENABLED", False),
            testing_notice_text=os.getenv(
                "TESTING_NOTICE_TEXT",
                "⚠️ Бот находится в тестировании. Данные могут быть изменены или утеряны.",
            ),
            database_path=Path(os.getenv("DATABASE_PATH", "data/ogorodom.sqlite3")),
            backup_dir=Path(os.getenv("BACKUP_DIR", "backups")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            poll_timeout_seconds=_int_env("POLL_TIMEOUT_SECONDS", 30),
            worker_interval_seconds=_int_env("WORKER_INTERVAL_SECONDS", 30),
            startup_backup_enabled=_bool_env("STARTUP_BACKUP_ENABLED", True),
            startup_backup_min_interval_seconds=_int_env(
                "STARTUP_BACKUP_MIN_INTERVAL_SECONDS", 300
            ),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow"),
            default_quiet_start=os.getenv("DEFAULT_QUIET_START", "22:00"),
            default_quiet_end=os.getenv("DEFAULT_QUIET_END", "08:00"),
            reminder_lead_minutes=_int_env("REMINDER_LEAD_MINUTES", 60),
        )

    def require_bot_token(self) -> None:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is required")
