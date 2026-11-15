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

The seed script creates one demo café, three demo accounts, two equipment items, one policy, one billing record, two demo claims, and fictional policy clauses. It is safe to run more than once. It refuses to run against `equipsure_test`.

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

Open http://localhost:5173. Sign in with a demo account, enter a claim id, and the claim, document checklist, and role-appropriate panels appear.

To find the demo claim ids:

```bash
docker compose exec -T db psql -U "$(grep ^POSTGRES_USER .env | cut -d= -f2)" -d equipsure -tAc "SELECT reference, id FROM claims ORDER BY reference;"
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

- **Authentication & RBAC:** Login with bcrypt-hashed passwords and JWT access tokens (`POLICYHOLDER`, `OPS`, `ADMIN`), role-based access control, and business/tenant-scoped claim isolation.
- **Policyholder claim registration:** `GET /api/claims/options` and `POST /api/claims` with `ClaimRegistrationPanel`, validating policy status, coverage period, covered equipment, and billing eligibility via simulated PolicyCenter and BillingCenter checks and allocating unique `CLM-XXXXXX` claim references via simulated ClaimCenter checks.
- **Simulated PolicyCenter & BillingCenter verification:** `GET /api/claims/{claim_id}/verification` and `ClaimVerificationPanel` exposing simulated policy validity, equipment coverage (`MOCK_POLICYCENTER`), and premium/account status (`MOCK_BILLINGCENTER`) checks.
- **Document upload, checklist, and review:** `GET/POST /api/claims/{claim_id}/documents`, `GET /api/claims/{claim_id}/documents/{document_id}`, `GET /api/claims/{claim_id}/checklist`, and `DocumentPanel` with magic-byte file-signature checks (`PDF`, `PNG`, `JPEG`), 10 MB size limit, SHA-256 hashing, officer/policyholder download, and terminal-status upload guards.
- **Claim workflow, approval, rejection, and withdrawal:** `POST /api/claims/{claim_id}/status` and `ClaimStatusPanel` enforcing legal transitions (`SUBMITTED` through `CLOSED`, `REJECTED`, and policyholder `WITHDRAWN`), system-driven document checklist transitions, required explanations, and persisted rejection reasons exposed on claim detail (`rejection_reason`).
- **Investigation officer assignment:** `GET /api/claims/officers`, `POST /api/claims/{claim_id}/assignment`, and `OfficerAssignmentPanel` persisting `assigned_officer_id` and `assigned_at` on `claims` (migration `0006_assignment_and_settlement.py`), displaying the assignee in the claim list and detail views, and locking reassignment after approval.
- **Simulated settlement tracking:** `GET/POST/PATCH /api/claims/{claim_id}/settlement` and `SettlementPanel` persisting simulated `ClaimSettlement` records (`claim_settlements` table in migration `0006_assignment_and_settlement.py`) with unique `STL-XXXXXX` references, `INR` (`₹`) default currency (plus `USD`, `EUR`, `GBP`), amount/coverage-limit/claimed-amount validation, and status transitions (`APPROVED` → `SETTLEMENT_IN_PROGRESS` → `SETTLED`). Explicitly simulated (`MOCK_CLAIMCENTER`) with no real payment transfer.
- **Claim history & append-only audit trail:** `GET /api/claims/{claim_id}/history` and `ClaimHistoryPanel` displaying chronological `claim_events` protected by a PostgreSQL append-only trigger.
- **Policyholder–officer messaging & notifications:** `GET/POST /api/claims/{claim_id}/messages` (`MessagesPanel`) and `GET /api/notifications` + `PATCH /api/notifications/{id}/read` (`NotificationsPanel`), notifying all active policyholders of a business on claim status changes.
- **Policy assistant & advisory AI assessment:** Keyword-retrieval policy assistant (`AssistantPanel`) and officer-only advisory claim assessment (`AssessmentPanel`) validated against approved demo clause IDs (`AI_PROVIDER=gemini` by default; model is configurable with `GEMINI_MODEL`).

## Not yet implemented

- Live Guidewire PolicyCenter, BillingCenter, or ClaimCenter connectivity (all Guidewire adapters are local database simulations).
- Real payment processing or bank/NEFT disbursements (settlement records are simulated only).
- The incident report generator.
- Retrieval-augmented generation with vector embeddings.
- Email/SMS or push notifications outside the in-app notification center.
- Gemini is the default provider; automated tests use deterministic fake-provider fixtures.

## Troubleshooting

- `ModuleNotFoundError: No module named 'app'`: run `pytest` or `uvicorn` from inside `backend/`.
- `zsh: command not found: docker`: run `export PATH="$HOME/.docker/bin:$PATH"` in that terminal.
- Frontend shows "API unreachable": check the backend is running on port 8000.
- Login says "Sign-in failed": check you typed the password from `.env` for that account.
- `npm run build` or `npm run lint` says "Missing script": you are in the project root; run them from `frontend/`.