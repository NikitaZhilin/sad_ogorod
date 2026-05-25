from __future__ import annotations

from ogorodom_bot.services.time_utils import format_local_datetime


REPEAT_LABELS = {
    "none": "без повтора",
    "daily": "каждый день",
    "weekly": "каждую неделю",
    "monthly": "каждый месяц",
    "yearly": "каждый год",
}

REFERENCE_TEXTS = {
    "watering": (
        "Полив\n\n"
        "Лучше поливать утром или вечером, когда нет активного солнца. "
        "Для большинства посадок важнее редкий глубокий полив, чем частый поверхностный."
    ),
    "mowing": (
        "Покос\n\n"
        "Не срезайте газон слишком низко в жару. После покоса удобно создать задачу на следующий покос через 7-14 дней."
    ),
    "treatment": (
        "Обработка\n\n"
        "Всегда фиксируйте препарат, дату и срок ожидания. После обработки добавляйте задачу проверки результата через несколько дней."
    ),
    "weeding": (
        "Прополка\n\n"
        "Удобно вести по зонам: так видно, где работы повторяются чаще всего."
    ),
    "fertilizing": (
        "Подкормка\n\n"
        "Записывайте состав и дозировку. Повторные подкормки лучше ставить задачами, чтобы не делать их раньше срока."
    ),
    "task_ideas": (
        "Идеи задач\n\n"
        "Полить, прополоть, проверить вредителей, обработать, подкормить, подвязать, замульчировать, покосить, убрать сухие листья, проверить укрытия."
    ),
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
        location = _location_line(task)
        lines.append(f"#{task['id']} {task['title']}\nСрок: {due}{location}{suffix}")
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
            location = _location_line(task)
            lines.append(f"#{task['id']} {task['title']}\nСрок: {due}{location}{wait}")
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
    location = _location_value(task)
    return (
        f"Задача #{task['id']}\n"
        f"{task['title']}\n\n"
        f"Место: {location}\n"
        f"Срок: {due}\n"
        f"Повтор: {repeat}\n"
        f"Напоминание: {remind}\n"
        f"Срок ожидания: {wait}\n"
        f"Описание: {description}"
    )


def task_confirmation(payload: dict, timezone_name: str) -> str:
    repeat = REPEAT_LABELS.get(payload.get("repeat_rule", "none"), "без повтора")
    due = format_local_datetime(payload.get("due_at"), timezone_name)
    description = payload.get("description") or "нет"
    location = payload.get("location_label") or "без привязки"
    return (
        "Проверьте задачу перед созданием:\n"
        f"Название: {payload['title']}\n"
        f"Описание: {description}\n"
        f"Место: {location}\n"
        f"Срок: {due}\n"
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


def plot_card(plot: dict, zones: list[dict]) -> str:
    lines = [f"Участок #{plot['id']}", plot["name"]]
    linked = [zone["name"] for zone in zones if zone.get("plot_id") == plot["id"]]
    if linked:
        lines.append("Зоны: " + ", ".join(linked))
    else:
        lines.append("Зон пока нет.")
    return "\n".join(lines)


def zone_card(zone: dict) -> str:
    plot = zone.get("plot_name") or "без участка"
    return f"Зона #{zone['id']}\n{zone['name']}\nУчасток: {plot}"


def reference_home() -> str:
    return "Справочник\n\nКороткие подсказки по типовым работам и идеи задач для участка."


def reference(topic: str) -> str:
    return REFERENCE_TEXTS.get(topic, reference_home())


def location_task_ideas(name: str) -> str:
    return (
        f"Возможные задачи для «{name}»\n\n"
        "Полить\n"
        "Прополоть\n"
        "Проверить вредителей\n"
        "Провести обработку\n"
        "Подкормить\n"
        "Стрижка травы\n"
        "Замульчировать\n"
        "Убрать сухие листья\n\n"
        "Любую из них можно добавить через «Новая задача» и привязать к этой зоне или участку."
    )


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


def _location_value(task: dict) -> str:
    if task.get("zone_name") and task.get("plot_name"):
        return f"{task['plot_name']} / {task['zone_name']}"
    if task.get("zone_name"):
        return task["zone_name"]
    if task.get("plot_name"):
        return task["plot_name"]
    return "не указано"


def _location_line(task: dict) -> str:
    value = _location_value(task)
    return "" if value == "не указано" else f"\nМесто: {value}"
