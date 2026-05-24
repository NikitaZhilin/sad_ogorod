# Deploy

## Docker Compose

Use a dedicated directory and project name so this bot does not collide with any existing Telegram, MTProto, VPN or Amnezia services.

```bash
sudo mkdir -p /opt/ogorodom
sudo chown "$USER":"$USER" /opt/ogorodom
cd /opt/ogorodom
git clone https://github.com/NikitaZhilin/sad_ogorod.git .
cp .env.example .env
$EDITOR .env
docker compose -p ogorodom up -d --build
docker compose -p ogorodom ps
docker compose -p ogorodom logs -f --tail=100
```

Update:

```bash
cd /opt/ogorodom
git pull --ff-only
docker compose -p ogorodom build
docker compose -p ogorodom run --rm ogorodom-bot python -m ogorodom_bot.manage migrate
docker compose -p ogorodom up -d
docker compose -p ogorodom logs --tail=100
```

Backup:

```bash
docker compose -p ogorodom run --rm ogorodom-bot python -m ogorodom_bot.manage backup
```

Dry-run напоминаний без отправки сообщений:

```bash
docker compose -p ogorodom run --rm ogorodom-worker python -m ogorodom_bot.worker --dry-run
docker compose -p ogorodom run --rm ogorodom-bot python -m ogorodom_bot.manage dry-run-reminders
```

Restore:

```bash
docker compose -p ogorodom down
docker compose -p ogorodom run --rm ogorodom-bot python -m ogorodom_bot.manage restore --source /app/backups/backup.sqlite3
docker compose -p ogorodom up -d
```

## Systemd Fallback

Systemd templates are in `deploy/systemd`. They assume:

- project path: `/opt/ogorodom`
- env file: `/opt/ogorodom/.env`
- Python virtualenv: `/opt/ogorodom/.venv`
- root-owned service files. Add a dedicated user only if `/opt` permissions allow it.

Install:

```bash
cd /opt/ogorodom
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo cp deploy/systemd/ogorodom-bot.service /etc/systemd/system/
sudo cp deploy/systemd/ogorodom-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ogorodom-bot ogorodom-worker
sudo systemctl status ogorodom-bot ogorodom-worker
```
