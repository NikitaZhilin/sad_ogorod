# Огородом

Telegram-бот для ведения огородных задач: участки, зоны, насаждения, повторяющиеся работы, напоминания, журнал действий, quiet hours, backup и диагностика.

## Возможности MVP-1

- Telegram bot через Bot API long polling.
- Кнопочный интерфейс: главное reply-меню, inline-действия и callback query.
- Пошаговые диалоги создания задач, участков, зон и насаждений с сохранением состояния в SQLite.
- Уведомление пользователей при обновлении бота один раз на новую `APP_VERSION`.
- SQLite база с миграциями при старте.
- Архитектура `bot -> services -> repositories -> db`.
- Участки, зоны, насаждения: растения, кустарники, деревья, декоративные и прочие объекты с привязкой к участку или зоне.
- Задачи со сроком, описанием, привязкой к участку/зоне/насаждению, напоминанием и повторами `daily`, `weekly`, `monthly`, `yearly`.
- Редактирование задач, участков и зон через кнопки.
- Справочник типовых работ и идеи задач для участка, зоны или насаждения.
- Отдельный worker для напоминаний.
- Quiet hours и включение/выключение уведомлений.
- Журнал действий.
- Backup/restore SQLite.
- Docker Compose и systemd fallback.
- Тесты сервисов и bot handlers.

## Команды бота

Основной пользовательский слой работает через кнопки: после `/start` бот показывает меню `Сегодня`, `Новая задача`, `Все задачи`, `Огород`, `Журнал`, `Справочник`, `Настройки`, `Помощь`. В диалогах создания задачи бот принимает даты в форматах `2026-05-25 12:00`, `25.05.2026 12:00`, `25.05 12:00`, `сегодня 12:00`, `завтра 9:00`, а также предлагает быстрые варианты срока. Команды ниже сохранены для обратной совместимости и быстрого ручного администрирования.

```text
/start или /help
/today
/task YYYY-MM-DD HH:MM | название | repeat=none|daily|weekly|monthly|yearly
/tasks
/done ID
/pause
/resume
/water [текст]
/mow [текст]
/treat [текст] [wait=3]
/log [текст]
/delete_me
/plot название
/plots
/zone название
/zones
/planting название [| YYYY-MM-DD]
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

Worker dry-run без отправки сообщений:

```bash
python -m ogorodom_bot.worker --dry-run
python -m ogorodom_bot.manage dry-run-reminders
```

Startup backup включен по умолчанию и защищен от слишком частого запуска:

```env
STARTUP_BACKUP_ENABLED=true
STARTUP_BACKUP_MIN_INTERVAL_SECONDS=300
```

## Уведомление об обновлении

Если `SEND_STARTUP_UPDATE_ON_BOOT=true`, бот при старте отправит всем зарегистрированным пользователям сообщение об обновлении один раз для каждой новой `APP_VERSION`.

```env
APP_VERSION=0.7.1-beta
SEND_STARTUP_UPDATE_ON_BOOT=true
STARTUP_UPDATE_MESSAGE=Упрощено добавление насаждений: овощи и ягоды вынесены в отдельную категорию, сорт больше не обязателен в кнопочном диалоге.
TESTING_NOTICE_ENABLED=true
TESTING_NOTICE_TEXT=⚠️ Бот находится в бета-тестировании. Данные могут быть изменены или утеряны.
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
