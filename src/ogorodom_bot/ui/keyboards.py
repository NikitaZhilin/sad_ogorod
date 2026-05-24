from __future__ import annotations

from typing import Any


def reply_keyboard(rows: list[list[str]]) -> dict[str, Any]:
    return {
        "keyboard": [[{"text": item} for item in row] for row in rows],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def inline_keyboard(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row] for row in rows
        ]
    }


def main_menu() -> dict[str, Any]:
    return reply_keyboard(
        [
            ["Сегодня", "Задачи"],
            ["Огород", "Журнал"],
            ["Настройки", "Помощь"],
            ["Отмена"],
        ]
    )


def cancel_inline() -> dict[str, Any]:
    return inline_keyboard([[("Отмена", "dialog:cancel")]])


def tasks_menu(tasks: list[dict]) -> dict[str, Any]:
    rows: list[list[tuple[str, str]]] = []
    for task in tasks:
        task_id = task["id"]
        rows.append(
            [
                ("Готово", f"task:done:{task_id}"),
                ("Подробнее", f"task:details:{task_id}"),
            ]
        )
        rows.append(
            [
                ("Отложить", f"task:snooze:{task_id}"),
                ("Пропустить", f"task:skip:{task_id}"),
            ]
        )
    rows.append([("Создать задачу", "tasks:new"), ("Обновить", "tasks:refresh")])
    return inline_keyboard(rows)


def today_menu(tasks: list[dict]) -> dict[str, Any]:
    rows: list[list[tuple[str, str]]] = []
    for task in tasks:
        task_id = task["id"]
        rows.append(
            [
                ("Готово", f"task:done:{task_id}"),
                ("Отложить", f"task:snooze:{task_id}"),
            ]
        )
        rows.append(
            [
                ("Пропустить", f"task:skip:{task_id}"),
                ("Подробнее", f"task:details:{task_id}"),
            ]
        )
    rows.append([("Обновить", "today:refresh")])
    return inline_keyboard(rows)


def snooze_menu(task_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("1 час", f"task:snooze1h:{task_id}"), ("Вечер", f"task:snoozeevening:{task_id}")],
            [("Завтра", f"task:snoozetomorrow:{task_id}")],
            [("Выбрать дату", f"task:snoozecustom:{task_id}")],
            [("Назад", "menu:today")],
        ]
    )


def skip_menu(task_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Без причины", f"task:skipnow:{task_id}")],
            [("Указать причину", f"task:skipreason:{task_id}")],
            [("Назад", "menu:today")],
        ]
    )


def task_details(task_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Готово", f"task:done:{task_id}")],
            [("Назад", "menu:tasks")],
        ]
    )


def repeat_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Без повтора", "task:repeat:none")],
            [("Каждый день", "task:repeat:daily"), ("Каждую неделю", "task:repeat:weekly")],
            [("Каждый месяц", "task:repeat:monthly"), ("Каждый год", "task:repeat:yearly")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def task_confirm() -> dict[str, Any]:
    return inline_keyboard([[("Создать", "task:create"), ("Отмена", "dialog:cancel")]])


def garden_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Участки", "garden:plots"), ("Зоны", "garden:zones")],
            [("Посадки", "garden:plantings")],
        ]
    )


def garden_list(section: str) -> dict[str, Any]:
    add_callbacks = {
        "plots": "plot:add",
        "zones": "zone:add",
        "plantings": "planting:add",
    }
    return inline_keyboard(
        [
            [("Добавить", add_callbacks[section])],
            [("Назад", "menu:garden")],
        ]
    )


def choose_plot(plots: list[dict]) -> dict[str, Any]:
    rows = [[(plot["name"], f"zone:plot:{plot['id']}")] for plot in plots]
    rows.append([("Без участка", "zone:plot:none")])
    rows.append([("Отмена", "dialog:cancel")])
    return inline_keyboard(rows)


def choose_zone(zones: list[dict]) -> dict[str, Any]:
    rows = [[(zone["name"], f"planting:zone:{zone['id']}")] for zone in zones]
    rows.append([("Без зоны", "planting:zone:none")])
    rows.append([("Отмена", "dialog:cancel")])
    return inline_keyboard(rows)


def journal_menu() -> dict[str, Any]:
    return inline_keyboard([[("Добавить запись", "log:add"), ("Обновить", "journal:refresh")]])


def work_type_menu(prefix: str = "logtype") -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Полив", f"{prefix}:watering"), ("Покос", f"{prefix}:mowing")],
            [("Обработка", f"{prefix}:treatment"), ("Другое", f"{prefix}:other")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def delete_me_confirm() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Да, удалить мои данные", "delete:confirm")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def settings_menu(notifications_enabled: bool) -> dict[str, Any]:
    notify_text = "Уведомления: вкл" if notifications_enabled else "Уведомления: выкл"
    return inline_keyboard(
        [
            [(notify_text, "settings:notify:toggle")],
            [("Тихие часы", "settings:quiet")],
            [("15 мин", "settings:remind:15"), ("30 мин", "settings:remind:30")],
            [("1 час", "settings:remind:60"), ("3 часа", "settings:remind:180")],
            [("Ввести свое", "settings:remind:custom")],
        ]
    )
