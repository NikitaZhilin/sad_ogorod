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
            ["Сегодня", "Новая задача"],
            ["Все задачи", "Огород"],
            ["Журнал", "Справочник"],
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
                (f"Открыть #{task_id}", f"task:details:{task_id}"),
                ("Готово", f"task:done:{task_id}"),
            ]
        )
    rows.append([("Новая задача", "tasks:new"), ("Обновить список", "tasks:refresh")])
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
    rows.append([("Новая задача", "tasks:new"), ("Обновить", "today:refresh")])
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
            [("Готово", f"task:done:{task_id}"), ("Изменить", f"task:edit:{task_id}")],
            [("Отложить", f"task:snooze:{task_id}"), ("Пропустить", f"task:skip:{task_id}")],
            [("К списку задач", "menu:tasks")],
        ]
    )


def task_edit_menu(task_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Название", f"task:edit_title:{task_id}"), ("Срок", f"task:edit_due:{task_id}")],
            [("Описание", f"task:edit_desc:{task_id}"), ("Место", f"task:edit_loc:{task_id}")],
            [("Повтор", f"task:edit_repeat:{task_id}")],
            [("К задаче", f"task:details:{task_id}")],
        ]
    )


def task_due_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Сегодня вечером", "task:due:today_evening")],
            [("Завтра утром", "task:due:tomorrow_morning"), ("Завтра вечером", "task:due:tomorrow_evening")],
            [("Ввести дату", "task:due:custom"), ("Без срока", "task:due:none")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def task_description_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Пропустить описание", "task:desc:skip")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def task_location_menu(zones: list[dict], plots: list[dict]) -> dict[str, Any]:
    rows: list[list[tuple[str, str]]] = []
    for zone in zones:
        prefix = f"{zone['plot_name']} / " if zone.get("plot_name") else ""
        rows.append([(f"{prefix}{zone['name']}", f"task:loc:z:{zone['id']}")])
    if not zones:
        for plot in plots:
            rows.append([(plot["name"], f"task:loc:p:{plot['id']}")])
    rows.append([("Без привязки", "task:loc:none")])
    rows.append([("Отмена", "dialog:cancel")])
    return inline_keyboard(rows)


def edit_task_location_menu(task_id: int, zones: list[dict], plots: list[dict]) -> dict[str, Any]:
    base = task_location_menu(zones, plots)["inline_keyboard"]
    rows: list[list[tuple[str, str]]] = []
    for row in base:
        converted = []
        for button in row:
            data = button["callback_data"]
            if data.startswith("task:loc:"):
                data = data.replace("task:loc:", f"task:eloc:{task_id}:", 1)
            converted.append((button["text"], data))
        rows.append(converted)
    rows[-1] = [("К задаче", f"task:details:{task_id}")]
    return inline_keyboard(rows)


def repeat_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Без повтора", "task:repeat:none")],
            [("Каждый день", "task:repeat:daily"), ("Каждую неделю", "task:repeat:weekly")],
            [("Каждый месяц", "task:repeat:monthly"), ("Каждый год", "task:repeat:yearly")],
            [("Отмена", "dialog:cancel")],
        ]
    )


def edit_repeat_menu(task_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Без повтора", f"task:er:{task_id}:none")],
            [("Каждый день", f"task:er:{task_id}:daily"), ("Каждую неделю", f"task:er:{task_id}:weekly")],
            [("Каждый месяц", f"task:er:{task_id}:monthly"), ("Каждый год", f"task:er:{task_id}:yearly")],
            [("К задаче", f"task:details:{task_id}")],
        ]
    )


def task_confirm() -> dict[str, Any]:
    return inline_keyboard([[("Создать задачу", "task:create"), ("Отмена", "dialog:cancel")]])


def garden_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Участки", "garden:plots"), ("Зоны", "garden:zones")],
            [("Посадки", "garden:plantings")],
        ]
    )


def garden_list(section: str, rows_data: list[dict] | None = None) -> dict[str, Any]:
    add_callbacks = {
        "plots": "plot:add",
        "zones": "zone:add",
        "plantings": "planting:add",
    }
    detail_prefix = {
        "plots": "plot:details",
        "zones": "zone:details",
        "plantings": "planting:details",
    }
    rows: list[list[tuple[str, str]]] = []
    for item in rows_data or []:
        rows.append([(f"Открыть #{item['id']}", f"{detail_prefix[section]}:{item['id']}")])
    rows.extend(
        [
            [("Добавить", add_callbacks[section])],
            [("Назад", "menu:garden")],
        ]
    )
    return inline_keyboard(
        rows
    )


def plot_details(plot_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Переименовать", f"plot:edit:{plot_id}"), ("Удалить", f"plot:delete:{plot_id}")],
            [("Что сделать здесь", f"ref:plot_tasks:{plot_id}")],
            [("К участкам", "garden:plots")],
        ]
    )


def zone_details(zone_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Переименовать", f"zone:edit:{zone_id}"), ("Удалить", f"zone:delete:{zone_id}")],
            [("Что сделать здесь", f"ref:zone_tasks:{zone_id}")],
            [("К зонам", "garden:zones")],
        ]
    )


def confirm_delete_plot(plot_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Да, удалить участок", f"plot:delete_confirm:{plot_id}")],
            [("Отмена", f"plot:details:{plot_id}")],
        ]
    )


def confirm_delete_zone(zone_id: int) -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Да, удалить зону", f"zone:delete_confirm:{zone_id}")],
            [("Отмена", f"zone:details:{zone_id}")],
        ]
    )


def reference_menu() -> dict[str, Any]:
    return inline_keyboard(
        [
            [("Полив", "ref:watering"), ("Покос", "ref:mowing")],
            [("Обработка", "ref:treatment"), ("Прополка", "ref:weeding")],
            [("Подкормка", "ref:fertilizing"), ("Идеи задач", "ref:task_ideas")],
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
