# Emdadyar (Phase 1 Foundation)

This repository currently implements **Phase 1** of the MVP from `PRODUCT_SPEC.md`:

- Basic FastAPI application setup
- SQLite + SQLAlchemy configuration
- Initial database schema foundation
- Minimal admin authentication foundation (session-based)
- Basic startup path and health endpoint
- Minimal database tests

No Bale bot, admin panel UI, messaging, or advanced request features are implemented yet.

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 (included for future admin templates)

## Project Structure

```text
app/
  main.py
  config.py
  database.py
  auth.py
  models/
    core.py
  routes/
    auth.py
    health.py
tests/
  test_database_foundation.py
```

## Local Development

### 1) Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Create environment file

```bash
cp .env.example .env
```

You should change at least:

- `SECRET_KEY`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`

### 4) Run the app

```bash
uvicorn app.main:app --reload
```

On startup, tables are created automatically in SQLite using `DATABASE_URL`.

If `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` are set, an initial admin user is created once.

### 5) Basic API checks

- Health: `GET /health`
- Login: `POST /auth/login` with JSON body:

```json
{
  "username": "admin",
  "password": "admin123"
}
```

- Current session admin: `GET /auth/me`
- Logout: `POST /auth/logout`

## Tests

Run:

```bash
pytest -q
```

Current tests cover basic database schema persistence and the single unfinished request constraint per `chat_id`.
