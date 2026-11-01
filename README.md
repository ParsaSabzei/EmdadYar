# Emdadyar

A simple monolithic request-management MVP for charity workflows.

## Stack

- Python 3.13.13
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 templates (admin panel)
- Balethon (Bale bot integration)
- Local filesystem uploads

## Requirements

- Linux-compatible environment
- Python **3.13.13**
- Bale bot token (for bot runtime and admin->beneficiary messaging)

## Setup

```bash
git clone <repo-url>
cd NEmdadYar

python3.13 -m venv .venv313
source .venv313/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Verify environment:

```bash
.venv313/bin/python --version
# expected: Python 3.13.13
```

## Configuration

Configure `.env` using `.env.example`.

Required/important variables:

- `SECRET_KEY` - session signing key
- `DATABASE_URL` - SQLite URL (default `sqlite:///./emdadyar.db`)
- `UPLOADS_DIR` - uploads root directory (default `uploads`)
- `BALE_BOT_TOKEN` - Bale bot token
- `ADMIN_USERNAME`, `ADMIN_PASSWORD` - initial admin bootstrap credentials

Backward-compatible fallback (optional):

- `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`

Session cookie options:

- `SESSION_COOKIE_SECURE` (`true`/`false`)
- `SESSION_COOKIE_SAMESITE` (`lax`/`strict`/`none`)

## Database initialization

Database tables are created automatically on app startup (`init_db()`).

## Run FastAPI app

```bash
.venv313/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run Bale bot (separate process)

```bash
.venv313/bin/python run_bale_bot.py
```

FastAPI and Bale bot are separate processes and should both run in deployment.

## Admin panel

- Login URL: `http://127.0.0.1:8000/admin/login`
- Initial admin is created automatically at startup if `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set (or fallback `INITIAL_ADMIN_*`).

## Upload storage

Uploaded files are stored under:

- `UPLOADS_DIR/requests/<request_id>/...`

`uploads/` is intentionally not publicly exposed as static files.

## Tests

```bash
.venv313/bin/pytest -q
```

## Simple Linux deployment (MVP)

Run as two long-lived processes:

1. FastAPI/Uvicorn
2. Bale bot process

Optional `systemd` examples:

### `/etc/systemd/system/emdadyar-web.service`

```ini
[Unit]
Description=Emdadyar FastAPI
After=network.target

[Service]
WorkingDirectory=/opt/emdadyar
ExecStart=/opt/emdadyar/.venv313/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
EnvironmentFile=/opt/emdadyar/.env
Restart=always

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/emdadyar-bot.service`

```ini
[Unit]
Description=Emdadyar Bale Bot
After=network.target

[Service]
WorkingDirectory=/opt/emdadyar
ExecStart=/opt/emdadyar/.venv313/bin/python run_bale_bot.py
EnvironmentFile=/opt/emdadyar/.env
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now emdadyar-web emdadyar-bot
```

## Known limitation

Real Bale API calls may fail in restricted environments with:

- `httpx.ProxyError: 511 Network Authentication Required`

This originates from environment/network proxy restrictions in the Balethon/httpx stack, not from Emdadyar business logic.
Automated tests mock Bale calls and do not require real Bale network access.
