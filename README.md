# EquipSure

EquipSure is a college project that simulates equipment-breakdown insurance claims for small businesses. It runs a FastAPI backend, a PostgreSQL database in Docker, and a React frontend.

All data is fictional. The insurance rules and policy clauses are prototype rules for demonstration only, and every AI output is advisory. See `docs/simulated-vs-real.md` for exactly what is real and what is simulated.

## Prerequisites

- Python 3.11 or newer (`python --version`)
- Node.js 20 or newer (`node --version`)
- Docker Desktop, running

## One-time setup

Run from the project root (`equipsure/`).

1. Create the Python environment inside `backend/`:

```bash
   python3 -m venv backend/.venv
   source backend/.venv/bin/activate
   pip install -r requirements.txt
```

2. Create your local environment file and set your own values:

```bash
   cp .env.example .env
```

   Edit `.env` and set `POSTGRES_PASSWORD`, `JWT_SECRET`, and the three `SEED_*_PASSWORD` values. Generate random secrets with:

```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

   Never commit `.env`. It is git-ignored.

3. Install the frontend packages:

```bash
   cd frontend
   npm install
   cd ..
```

## Start the database

From the project root:

```bash
docker compose up -d
docker compose ps        # db should show "healthy"
```

The first start creates the `equipsure` and `equipsure_test` databases.

## Set up the database and demo data

From `backend/` with the virtual environment active:

```bash
cd backend
set -a; source ../.env; set +a
alembic upgrade head
PYTHONPATH=. python scripts/seed.py
```

The seed script creates one demo café, three demo accounts, two equipment items, one policy, one billing record, one claim, and fictional policy clauses. It is safe to run more than once. It refuses to run against `equipsure_test`.

Demo accounts (passwords are the values you set in `.env`):

| Role | Email |
|---|---|
| Café owner (POLICYHOLDER) | `cafe.owner@equipsure.demo` |
| OPS officer | `ops.officer@equipsure.demo` |
| Administrator | `admin@equipsure.demo` |

## Run the backend

In one terminal:

```bash
cd backend
source .venv/bin/activate
set -a; source ../.env; set +a
uvicorn app.main:app --port 8000
```

Check it: http://localhost:8000/api/health and the API docs at http://localhost:8000/docs

## Run the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Sign in with a demo account, enter a claim id, and the claim, document checklist, and (for OPS) the advisory assessment appear.

To find the demo claim id:

```bash
docker compose exec -T db psql -U "$(grep ^POSTGRES_USER .env | cut -d= -f2)" -d equipsure -tAc "SELECT id FROM claims WHERE reference='DEMO-000001';"
```

## Run the tests

Backend (from `backend/`):

```bash
pytest -v
```

Frontend (from `frontend/`):

```bash
npm run build
npm run lint
```

Tests use the separate `equipsure_test` database and never touch development data.

## What is implemented

- Login with bcrypt-hashed passwords and JWT access tokens; role and business-scoped access checks.
- Claim lookup, required-document checklist, and document upload with file-signature checks and a size limit.
- Claim status workflow with an append-only audit trail, including system-driven document status moves and explicit OPS moves.
- Claim messages and in-app notifications (API only; no UI yet).
- Mock PolicyCenter, BillingCenter, and ClaimCenter adapters, labelled as simulated.
- AI document classification and claim assessment, using a fake provider by default, with output validated against the approved clause list. Gemini is wired but optional, and only synthetic documents should be sent.
- Frontend: login, claim view, document panel, and OPS-only advisory assessment panel.

## Not yet implemented

- A UI for notifications and messages.
- The incident report generator and the policy-grounded question-answering assistant.
- Real Guidewire integration, real payments, and real insurer decisions.

## Troubleshooting

- `ModuleNotFoundError: No module named 'app'`: run `pytest` or `uvicorn` from inside `backend/`.
- `zsh: command not found: docker`: run `export PATH="$HOME/.docker/bin:$PATH"` in that terminal.
- Frontend shows "API unreachable": check the backend is running on port 8000.
- Login says "Sign-in failed": check you typed the password from `.env` for that account.