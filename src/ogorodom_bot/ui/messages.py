from __future__ import annotations

from ogorodom_bot.services.time_utils import format_local_datetime


REPEAT_LABELS = {
    "none": "без повтора",
    "daily": "каждый день",
    "weekly": "каждую неделю",
    "monthly": "каждый месяц",
    "yearly": "каждый год",
}


def welcome() -> str:
    return (
        "Огородом\n\n"
        "Я помогу не забывать работы по участкам, посадкам и обработкам.\n\n"
        "Начните с кнопки «Новая задача» или откройте «Сегодня», чтобы увидеть ближайшие дела. "
        "Старые команды тоже работают."
    )


def tasks_list(tasks: list[dict], timezone_name: str) -> str:
    if not tasks:
        return "Список задач пуст.\n\nНажмите «Новая задача», чтобы добавить первое дело."
    lines = ["Все открытые задачи"]
    for task in tasks:
        due = format_local_datetime(task["due_at"], timezone_name)
        repeat = REPEAT_LABELS.get(task["repeat_rule"], task["repeat_rule"])
        suffix = "" if task["repeat_rule"] == "none" else f"\nПовтор: {repeat}"
        lines.append(f"#{task['id']} {task['title']}\nСрок: {due}{suffix}")
    return "\n\n".join(lines)


def today(data: dict[str, list[dict]], timezone_name: str) -> str:
    sections = [
        ("Просрочено", data["overdue"]),
        ("Сегодня", data["today"]),
        ("Ближайшие 3 дня", data["upcoming"]),
    ]
    if not any(rows for _, rows in sections):
        return "На сегодня и ближайшие 3 дня задач нет.\n\nМожно добавить новую задачу кнопкой ниже."
    lines: list[str] = ["Сегодня и ближайшие дела"]
    for title, rows in sections:
        if not rows:
            continue
        lines.append(f"\n{title}:")
        for task in rows:
            due = format_local_datetime(task["due_at"], timezone_name)
            wait = ""
            if task.get("wait_until_date"):
                wait = f"\nСрок ожидания до: {format_local_datetime(task['wait_until_date'], timezone_name)}"
            lines.append(f"#{task['id']} {task['title']}\nСрок: {due}{wait}")
    return "\n".join(lines)


def task_card(task: dict, timezone_name: str) -> str:
    due = format_local_datetime(task["due_at"], timezone_name)
    repeat = REPEAT_LABELS.get(task["repeat_rule"], task["repeat_rule"])
    description = task["description"] or "нет"
    remind = format_local_datetime(task["remind_at"], timezone_name) if task["remind_at"] else "нет"
    wait = (
        format_local_datetime(task["wait_until_date"], timezone_name)
        if task.get("wait_until_date")
        else "нет"
    )
    return (
        f"Задача #{task['id']}\n"
        f"{task['title']}\n\n"
        f"Срок: {due}\n"
        f"Повтор: {repeat}\n"
        f"Напоминание: {remind}\n"
        f"Срок ожидания: {wait}\n"
        f"Описание: {description}"
    )


def task_confirmation(payload: dict, timezone_name: str) -> str:
    repeat = REPEAT_LABELS.get(payload.get("repeat_rule", "none"), "без повтора")
    return (
        "Проверьте задачу перед созданием:\n"
        f"Название: {payload['title']}\n"
        f"Срок: {format_local_datetime(payload['due_at'], timezone_name)}\n"
        f"Повтор: {repeat}\n"
        f"Напоминание будет рассчитано по настройкам."
    )


def garden_home() -> str:
    return "Огород\n\nЗдесь хранятся участки, зоны и посадки. Выберите, что открыть."


def garden_items(title: str, rows: list[dict]) -> str:
    if not rows:
        return f"{title}: пока пусто."
    lines = [f"{title}:"]
    for row in rows:
        extra = ""
        if "plot_name" in row and row["plot_name"]:
            extra = f" ({row['plot_name']})"
        if "zone_name" in row and row["zone_name"]:
            extra = f" ({row['zone_name']})"
        if row.get("variety"):
            extra += f", сорт: {row['variety']}"
        lines.append(f"#{row['id']} {row['name']}{extra}")
    return "\n".join(lines)


def journal(rows: list[dict]) -> str:
    if not rows:
        return "Журнал пока пуст.\n\nЗдесь будут поливы, покосы, обработки и другие записи."
    lines = ["Журнал работ"]
    for row in rows:
        wait = f" Ожидание до: {row['wait_until_date']}" if row.get("wait_until_date") else ""
        lines.append(f"#{row['id']} {row['created_at']} - {row['note']}{wait}")
    return "\n".join(lines)


def settings(settings: dict, timezone_name: str) -> str:
    enabled = "включены" if settings["notifications_enabled"] else "выключены"
    return (
        "Настройки\n"
        f"Уведомления: {enabled}\n"
        f"Тихие часы: {settings['quiet_start']}-{settings['quiet_end']}\n"
        f"Напоминать за: {settings['reminder_lead_minutes']} мин.\n"
        f"Таймзона: {timezone_name}"
    )
