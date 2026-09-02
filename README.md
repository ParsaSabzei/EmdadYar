# Emdadyar (Phases 1-4)

Implemented so far:

- **Phase 1**: FastAPI + SQLite + SQLAlchemy foundation
- **Phase 2**: Dynamic service/request business logic
- **Phase 3**: Bale bot integration (Balethon)
- **Phase 4**: Simple server-rendered admin panel

Not implemented yet:

- Advanced search phase
- Advanced messaging features/history
- Deployment/finalization phase items

## Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 templates
- Balethon

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set at least in `.env`:

- `SECRET_KEY`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `BALE_BOT_TOKEN` (needed for bot + admin send message)

### Start FastAPI

```bash
uvicorn app.main:app --reload
```

### Start Bale bot (separate process)

```bash
python run_bale_bot.py
```

## Admin panel

Open:

- `GET /admin/login`

Main routes:

- `GET /admin` dashboard
- `GET /admin/services` + service/field/status management
- `GET /admin/requests` request list with service/status filtering
- `GET /admin/requests/{id}` request details, status update, message send

## Tests

```bash
pytest -q
```
