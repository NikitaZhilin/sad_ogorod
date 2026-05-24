from __future__ import annotations


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
        "Основные действия доступны кнопками внизу: задачи, огород, журнал и настройки. "
        "Текстовые команды тоже продолжают работать."
    )


def tasks_list(tasks: list[dict]) -> str:
    if not tasks:
        return "Открытых задач нет. Можно создать первую задачу кнопкой ниже."
    lines = ["Открытые задачи:"]
    for task in tasks:
        due = task["due_at"] or "без срока"
        repeat = REPEAT_LABELS.get(task["repeat_rule"], task["repeat_rule"])
        lines.append(f"#{task['id']} {due}\n{task['title']}\nПовтор: {repeat}")
    return "\n\n".join(lines)


def task_card(task: dict) -> str:
    due = task["due_at"] or "без срока"
    repeat = REPEAT_LABELS.get(task["repeat_rule"], task["repeat_rule"])
    description = task["description"] or "нет"
    remind = task["remind_at"] or "нет"
    return (
        f"Задача #{task['id']}\n"
        f"Название: {task['title']}\n"
        f"Срок: {due}\n"
        f"Повтор: {repeat}\n"
        f"Напоминание: {remind}\n"
        f"Описание: {description}"
    )


def task_confirmation(payload: dict) -> str:
    repeat = REPEAT_LABELS.get(payload.get("repeat_rule", "none"), "без повтора")
    return (
        "Проверьте задачу:\n"
        f"Название: {payload['title']}\n"
        f"Срок: {payload['due_at']}\n"
        f"Повтор: {repeat}\n"
        f"Напоминание будет рассчитано по настройкам."
    )


def garden_home() -> str:
    return "Огород: выберите раздел."


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
        return "Журнал пока пуст. Здесь появятся созданные задачи, посадки и выполненные работы."
    return "\n".join(
        ["Журнал:"] + [f"#{row['id']} {row['created_at']} - {row['note']}" for row in rows]
    )


def settings(settings: dict, timezone_name: str) -> str:
    enabled = "включены" if settings["notifications_enabled"] else "выключены"
    return (
        "Настройки:\n"
        f"Уведомления: {enabled}\n"
        f"Тихие часы: {settings['quiet_start']}-{settings['quiet_end']}\n"
        f"Напоминать за: {settings['reminder_lead_minutes']} мин.\n"
        f"Таймзона: {timezone_name}"
    )
