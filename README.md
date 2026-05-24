# Огородом

Telegram-бот для ведения огородных задач: участки, зоны, посадки, повторяющиеся работы, напоминания, журнал действий, quiet hours, backup и диагностика.

## Возможности MVP-1

- Telegram bot через Bot API long polling.
- Кнопочный интерфейс: главное reply-меню, inline-действия и callback query.
- Пошаговые диалоги создания задач, участков, зон и посадок с сохранением состояния в SQLite.
- SQLite база с миграциями при старте.
- Архитектура `bot -> services -> repositories -> db`.
- Участки, зоны, посадки.
- Задачи со сроком, напоминанием и повторами `daily`, `weekly`, `monthly`, `yearly`.
- Отдельный worker для напоминаний.
- Quiet hours и включение/выключение уведомлений.
- Журнал действий.
- Backup/restore SQLite.
- Docker Compose и systemd fallback.
- Тесты сервисов и bot handlers.

## Команды бота

Основной пользовательский слой работает через кнопки: после `/start` бот показывает меню `Задачи`, `Огород`, `Журнал`, `Настройки`, `Помощь`. Команды ниже сохранены для обратной совместимости и быстрого ручного администрирования.

```text
/start или /help
/task YYYY-MM-DD HH:MM | название | repeat=none|daily|weekly|monthly|yearly
/tasks
/done ID
/plot название
/plots
/zone название
/zones
/planting название | сорт | YYYY-MM-DD
/plantings
/journal
/settings quiet 22:00 08:00
/settings notify on|off
/backup
/diag
```

## Локальный запуск

```bash
cp .env.example .env
# заполнить BOT_TOKEN
python -m ogorodom_bot.manage migrate
python -m ogorodom_bot.bot
```

В отдельном процессе:

```bash
python -m ogorodom_bot.worker
```

Если запускаете без установки пакета, задайте:

```bash
export PYTHONPATH=src
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m ogorodom_bot.manage migrate
```

## Docker

```bash
cp .env.example .env
docker compose -p ogorodom up -d --build
docker compose -p ogorodom logs -f --tail=100
```

## Backup и диагностика

```bash
python -m ogorodom_bot.manage backup
python -m ogorodom_bot.manage diag
python -m ogorodom_bot.manage restore --source backups/ogorodom-YYYYMMDDTHHMMSSZ.sqlite3
```

## Тесты

```bash
$env:PYTHONPATH='src'  # PowerShell
python -m unittest discover
```

## VPS

Подробная инструкция: `deploy/README.md`.

Рекомендуемая безопасная схема деплоя:

- отдельная директория `/opt/ogorodom`;
- отдельный Docker Compose project name `ogorodom`;
- отдельные контейнеры `ogorodom-bot` и `ogorodom-worker`;
- отдельные volumes `ogorodom_data` и `ogorodom_backups`;
- `.env` только на VPS, без коммита в Git.
