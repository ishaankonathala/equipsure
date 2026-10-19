# EquipSure

EquipSure is an AI-powered equipment breakdown insurance claims automation platform. This repository currently provides the API foundation: a FastAPI backend with a health endpoint and basic configuration.

## Prerequisites

- Python 3.11 or newer. Check with: `python --version`

## Setup

Run these steps from the project root (`equipsure/`):

1. Create a virtual environment inside `backend/`:

   ```bash
   python -m venv backend/.venv
   ```

2. Activate it:

   - macOS/Linux: `source backend/.venv/bin/activate`
   - Windows PowerShell: `backend\.venv\Scripts\Activate.ps1`

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment file:

   - macOS/Linux: `cp .env.example .env`
   - Windows: `copy .env.example .env`

## Run tests

```bash
cd backend
pytest
cd ..
```

## Run the server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Then verify:

- Health: http://localhost:8000/api/health
- Interactive docs: http://localhost:8000/docs

## Database (Docker)

From the project root:

```bash
docker compose up -d
docker compose ps
docker compose down
```

`docker compose down` keeps data. To reset data (destructive): `docker compose down -v`.

The init script creates `equipsure_test` only on the first start of a new volume.

## Migrations

From `backend/`:

```bash
alembic upgrade head
alembic current
alembic downgrade -1
```

Migrations target the database in `.env` (`POSTGRES_DB`); tests use a separate database.

## Troubleshooting

If you see `ModuleNotFoundError: No module named 'app'`, make sure you are running `pytest` or `uvicorn` from inside the `backend/` directory.
