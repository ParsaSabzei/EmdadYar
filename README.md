# Emdadyar (Phases 1-5)

Implemented so far:

- **Phase 1**: FastAPI + SQLite + SQLAlchemy foundation
- **Phase 2**: Dynamic service/request business logic
- **Phase 3**: Bale bot integration (Balethon)
- **Phase 4**: Simple server-rendered admin panel
- **Phase 5**: Search, request deletion, file storage/serving, admin->beneficiary messaging

Not implemented yet:

- Phase 6 final hardening/deployment work

## Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 templates
- Balethon

## Run locally

```bash
python -m venv .venv313
source .venv313/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set at least in `.env`:

- `SECRET_KEY`
- `DATABASE_URL`
- `UPLOADS_DIR` (default: `uploads`)
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `BALE_BOT_TOKEN` (for bot + admin messaging)

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
- `GET /admin/requests` request list with service/status filters + search by name/national ID/tracking code
- `GET /admin/requests/{id}` request details, status update, file access, request deletion, message send

## File handling (Phase 5)

- Uploaded files are stored under `UPLOADS_DIR/requests/<request_id>/`
- Allowed types: PDF, JPG, JPEG, PNG
- Max size: 10 MB
- Stored DB path is safe generated path
- Original filename is preserved as metadata

## Tests

```bash
.venv313/bin/pytest -q
```
