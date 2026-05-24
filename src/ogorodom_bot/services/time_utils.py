from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_local_datetime(raw: str, timezone_name: str) -> datetime:
    raw = raw.strip()
    if len(raw) == 10:
        raw = raw + " 09:00"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M"):
        try:
            local = datetime.strptime(raw, fmt)
            return local.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("date must be YYYY-MM-DD HH:MM")


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def add_repeat(dt: datetime, repeat_rule: str) -> datetime | None:
    if repeat_rule == "none":
        return None
    if repeat_rule == "daily":
        return dt + timedelta(days=1)
    if repeat_rule == "weekly":
        return dt + timedelta(weeks=1)
    if repeat_rule == "monthly":
        month = dt.month + 1
        year = dt.year
        if month > 12:
            month = 1
            year += 1
        day = min(dt.day, _days_in_month(year, month))
        return dt.replace(year=year, month=month, day=day)
    if repeat_rule == "yearly":
        try:
            return dt.replace(year=dt.year + 1)
        except ValueError:
            return dt.replace(year=dt.year + 1, day=28)
    raise ValueError("unsupported repeat rule")


def quiet_adjusted(send_at: datetime, quiet_start: str, quiet_end: str, tz_name: str) -> datetime:
    local = send_at.astimezone(ZoneInfo(tz_name))
    start = _parse_time(quiet_start)
    end = _parse_time(quiet_end)
    if not _is_quiet(local.time(), start, end):
        return send_at
    if start < end:
        adjusted = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    else:
        if local.time() >= start:
            adjusted = (local + timedelta(days=1)).replace(
                hour=end.hour, minute=end.minute, second=0, microsecond=0
            )
        else:
            adjusted = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    return adjusted.astimezone(timezone.utc)


def _parse_time(raw: str) -> time:
    hour, minute = raw.split(":", 1)
    return time(int(hour), int(minute))


def _is_quiet(value: time, start: time, end: time) -> bool:
    if start < end:
        return start <= value < end
    return value >= start or value < end


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
