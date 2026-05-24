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


@dataclass(frozen=True)
class Settings:
    bot_token: str
    app_env: str
    database_path: Path
    backup_dir: Path
    log_level: str
    poll_timeout_seconds: int
    worker_interval_seconds: int
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
            database_path=Path(os.getenv("DATABASE_PATH", "data/ogorodom.sqlite3")),
            backup_dir=Path(os.getenv("BACKUP_DIR", "backups")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            poll_timeout_seconds=_int_env("POLL_TIMEOUT_SECONDS", 30),
            worker_interval_seconds=_int_env("WORKER_INTERVAL_SECONDS", 30),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow"),
            default_quiet_start=os.getenv("DEFAULT_QUIET_START", "22:00"),
            default_quiet_end=os.getenv("DEFAULT_QUIET_END", "08:00"),
            reminder_lead_minutes=_int_env("REMINDER_LEAD_MINUTES", 60),
        )

    def require_bot_token(self) -> None:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is required")
