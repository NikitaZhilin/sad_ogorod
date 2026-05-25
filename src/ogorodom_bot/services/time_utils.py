from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MONTH_NAMES = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}

MONTH_NUMBERS = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_local_datetime(raw: str, timezone_name: str) -> datetime:
    raw = _normalize_datetime_input(raw)
    tz = ZoneInfo(timezone_name)
    lowered = raw.lower()
    for prefix, day_offset in (("сегодня ", 0), ("завтра ", 1)):
        if lowered.startswith(prefix):
            time_part = raw[len(prefix) :].strip()
            parsed_time = _parse_time_flexible(time_part)
            base = datetime.now(tz).date() + timedelta(days=day_offset)
            local = datetime.combine(base, parsed_time, tzinfo=tz)
            return local.astimezone(timezone.utc)

    current_year = datetime.now(tz).year
    if re.match(r"^\d{1,2}\.\d{1,2}\s+\d{1,2}:\d{2}$", raw):
        raw = f"{raw[: raw.index(' ')]}.{current_year}{raw[raw.index(' '):]}"

    if len(raw) == 10:
        raw = raw + " 09:00"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M"):
        try:
            local = datetime.strptime(raw, fmt)
            return local.replace(tzinfo=tz).astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("date must be YYYY-MM-DD HH:MM")


def format_local_datetime(raw: str | None, timezone_name: str) -> str:
    if not raw:
        return "без срока"
    dt = parse_iso(raw)
    return dt.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")


def format_month(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month]} {year}"


def parse_planting_date(raw: str, timezone_name: str) -> str | None:
    value = raw.strip().lower()
    value = value.rstrip(".,; ")
    value = re.sub(r"\s+", " ", value)
    if value in {"", "-", "не знаю", "неизвестно"}:
        return None

    tz = ZoneInfo(timezone_name)
    current_year = datetime.now(tz).year

    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
    if match:
        year, month, day = map(int, match.groups())
        datetime(year, month, day)
        return f"{day:02d}.{month:02d}.{year}"

    match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", value)
    if match:
        day, month, year = map(int, match.groups())
        datetime(year, month, day)
        return f"{day:02d}.{month:02d}.{year}"

    match = re.match(r"^(\d{1,2})\.(\d{1,2})$", value)
    if match:
        day, month = map(int, match.groups())
        datetime(current_year, month, day)
        return f"{day:02d}.{month:02d}.{current_year}"

    match = re.match(r"^(\d{4})-(\d{1,2})$", value)
    if match:
        year, month = map(int, match.groups())
        if not 1 <= month <= 12:
            raise ValueError("month must be 1..12")
        return format_month(year, month)

    match = re.match(r"^(\d{1,2})\.(\d{4})$", value)
    if match:
        month, year = map(int, match.groups())
        if not 1 <= month <= 12:
            raise ValueError("month must be 1..12")
        return format_month(year, month)

    match = re.match(r"^([а-яё]+)(?:\s+(\d{4}))?$", value)
    if match:
        month_name, year_raw = match.groups()
        month = MONTH_NUMBERS.get(month_name)
        if month is None:
            raise ValueError("unknown month")
        year = int(year_raw) if year_raw else current_year
        return format_month(year, month)

    if re.match(r"^\d{4}$", value):
        return value

    raise ValueError("unsupported planting date")


def local_day_bounds(timezone_name: str, day_offset: int = 0) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    day = datetime.now(tz).date() + timedelta(days=day_offset)
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def snooze_target(option: str, timezone_name: str) -> datetime:
    now = utc_now()
    tz = ZoneInfo(timezone_name)
    local_now = now.astimezone(tz)
    if option == "1h":
        return now + timedelta(hours=1)
    if option == "evening":
        target = local_now.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= local_now:
            target = target + timedelta(days=1)
        return target.astimezone(timezone.utc)
    if option == "tomorrow":
        target = (local_now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        return target.astimezone(timezone.utc)
    raise ValueError("unsupported snooze option")


def parse_wait_until(raw: str, timezone_name: str) -> str:
    value = raw.strip().lower()
    if value.endswith("дней"):
        value = value[:-4].strip()
    elif value.endswith("дня"):
        value = value[:-3].strip()
    elif value.endswith("день"):
        value = value[:-4].strip()
    if value.isdigit():
        return iso(utc_now() + timedelta(days=int(value)))
    return iso(parse_local_datetime(raw, timezone_name))


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


def _parse_time_flexible(raw: str) -> time:
    raw = raw.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", raw):
        raise ValueError("time must be H:MM")
    return _parse_time(raw)


def _normalize_datetime_input(raw: str) -> str:
    raw = raw.strip()
    raw = raw.rstrip(".,; ")
    raw = re.sub(r"\s+", " ", raw)
    raw = raw.replace("T", " ")
    return raw


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
