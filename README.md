# Emdadyar (Phases 1-3)

This repository currently implements:

- **Phase 1**: FastAPI + database foundation
- **Phase 2**: Dynamic services and request business logic
- **Phase 3**: Bale bot integration using **Balethon** (beneficiary flow)

Not implemented yet:

- Admin panel UI
- Search pages
- Admin messaging
- Permanent file storage pipeline
- Deployment/finalization phases

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 (for later admin templates)
- Balethon

## Project Structure

```text
app/
  main.py
  config.py
  database.py
  auth.py
  models/
    core.py
  services/
    core.py
    bot_flow.py
  routes/
    auth.py
    health.py
  bale/
    bot.py
    handlers.py
    keyboards.py
    states.py
tests/
  test_database_foundation.py
  test_phase2_business_logic.py
  test_phase3_bale_handlers.py
run_bale_bot.py
```

## Local Development

### 1) Create and activate virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

```bash
cp .env.example .env
```

Set at least:

- `SECRET_KEY`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `BALE_BOT_TOKEN` (for running the bot)

### 4) Run FastAPI app

```bash
uvicorn app.main:app --reload
```

### 5) Run Bale bot process

```bash
python run_bale_bot.py
```

The bot process is intentionally separate from FastAPI.

## Beneficiary Bot Flow (Phase 3)

- `/start` shows active services
- `New Request` -> select active service
- Dynamic fields are asked in configured order (TEXT/NUMBER/FILE)
- Single unfinished request per beneficiary (`chat_id`)
- Submit request -> tracking code shown
- `My Requests` -> list + details
- `Cancel Current Request` -> cancels unfinished request

## Tests

Run all tests:

```bash
pytest -q
```
