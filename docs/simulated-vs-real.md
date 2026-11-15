# Simulated vs Real

## Purpose

EquipSure is a college project that simulates equipment-breakdown insurance claims. It does not connect to a real insurer or a real Guidewire environment, and its seeded demo records are fictional rather than real customer data.

## Real and Implemented

| Area | What runs in this codebase |
|---|---|
| Authentication | Bcrypt password hashing and JWT login are implemented in `backend/app/core/security.py` and `backend/app/api/routes/auth.py`. |
| Authorization & tenant isolation | Role checks (`POLICYHOLDER`, `OPS`, `ADMIN`) and business-scoped claim isolation (`404` for cross-business access, `403` for disallowed role actions) are implemented in `backend/app/core/deps.py`, `backend/app/services/claims.py`, and route handlers in `backend/app/api/routes/claims.py` and `backend/app/api/routes/claim_list.py`. |
| Database schema | PostgreSQL models and Alembic migrations `0001` through `0006` (`0006_assignment_and_settlement.py`) define the implemented schema, including `claims` officer-assignment columns (`assigned_officer_id`, `assigned_at`) and the `claim_settlements` table. |
| Claim registration | Policyholders register new claims via `GET /api/claims/options` and `POST /api/claims` (`backend/app/services/claims.py`), enforcing `run_submission_checks`, allocating a unique `CLM-XXXXXX` reference, and writing the initial `SUBMITTED` audit event. |
| Claim workflow & audit history | `backend/app/workflow/transitions.py` and `backend/app/workflow/service.py` implement allowed status transitions (`SUBMITTED` through `CLOSED`, `REJECTED` with persisted `rejection_reason`, and policyholder `WITHDRAWN`) and append-only audit events in `claim_events` (exposed via `GET /api/claims/{claim_id}/history`); a PostgreSQL trigger rejects event updates and deletes. |
| Officer assignment | `OPS` and `ADMIN` officers list assignable staff (`GET /api/claims/officers`) and assign investigators (`POST /api/claims/{claim_id}/assignment`), persisting `assigned_officer_id` and `assigned_at`, advancing `UNDER_REVIEW` claims to `INVESTIGATION_ASSIGNED`, and locking reassignment once a claim is approved or terminal. |
| Simulated settlement tracking | `GET/POST/PATCH /api/claims/{claim_id}/settlement` and `backend/app/models/settlement.py` (`claim_settlements`) persist simulated settlement records (`STL-XXXXXX` reference, `INR` default currency plus `USD`/`EUR`/`GBP`, amount validated against `claim.amount_claimed` and `policy.coverage_limit`, status `IN_PROGRESS` / `SETTLED`, and `settled_at` timestamp). |
| Documents | Uploads (`POST /api/claims/{claim_id}/documents`) are checked against magic-byte file signatures (`PDF`, `PNG`, `JPEG`), a 10 MB size limit, and terminal-status guards in `backend/app/services/documents.py` and `backend/app/api/routes/claims.py`; `backend/app/services/document_storage.py` stores files privately under `STORAGE_DIR` on local disk, and `GET /api/claims/{claim_id}/documents` + `GET /api/claims/{claim_id}/documents/{document_id}` provide listing and download. |
| Messages and notifications | Authenticated claim messages (`GET/POST /api/claims/{claim_id}/messages`) and user-scoped in-app notifications (`GET /api/notifications`, `PATCH /api/notifications/{id}/read`) are persisted and served by the API, notifying all active policyholders of a business on status transitions. These are in-app records, not email or push delivery. |
| Policy assistant | A keyword-retrieval assistant over the approved demo clauses (`backend/app/services/assistant_retrieval.py`, `backend/app/services/assistant.py`). It cites only retrieved clause IDs and refuses when nothing matches. It is not retrieval-augmented generation with embeddings. |
| AI assessment | Document classification and claim assessment are validated against approved clause IDs and must be advisory. Gemini is the default provider (`AI_PROVIDER=gemini`) for assessment and assistant generation. Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL`; tests inject the fake provider for deterministic, offline coverage. AI outputs remain advisory and are validated before use. |
| Frontend (React, TypeScript) | Sign-in and sign-out, policyholder claim registration (`ClaimRegistrationPanel`), claim dashboard list (`ClaimList`), claim detail view (`ClaimView`), simulated PolicyCenter & BillingCenter verification (`ClaimVerificationPanel`), chronological history timeline (`ClaimHistoryPanel`), officer assignment (`OfficerAssignmentPanel`), simulated settlement tracking (`SettlementPanel`), status changes and policyholder withdrawal (`ClaimStatusPanel`), document checklist/upload/download (`DocumentPanel`), OPS-only advisory assessment (`AssessmentPanel`), claim messaging (`MessagesPanel`), notifications with mark-as-read (`NotificationsPanel`), and the policy assistant (`AssistantPanel`). The access token is kept in memory only. |

## Simulated Guidewire-Aligned Adapters

| Area | Mock module | What it does | What it does NOT do |
|---|---|---|---|
| PolicyCenter | `backend/app/integrations/mock_policycenter.py` | Reads local policy data, checks policy validity, and checks whether equipment is linked through `policy_equipment`. Source label: `MOCK_POLICYCENTER`. | It does not contact a live Guidewire PolicyCenter instance or verify coverage with an external insurer. |
| BillingCenter | `backend/app/integrations/mock_billingcenter.py` | Reads local billing records and computes effective account and record statuses for an as-of date. Source label: `MOCK_BILLINGCENTER`. | It does not process real payments or contact an external Guidewire BillingCenter system. |
| ClaimCenter | `backend/app/integrations/mock_claimcenter.py` and `backend/app/services/claims.py` | Checks claim reference uniqueness, reads local claim status history, and tracks simulated claim settlements (`claim_settlements`). Source label: `MOCK_CLAIMCENTER`. | It does not contact a live Guidewire ClaimCenter system or execute real bank/payment transfers. |
| Combined submission & verification checks | `backend/app/integrations/submission_checks.py` and `backend/app/services/claims.py` | Combines PolicyCenter validity and equipment results with the BillingCenter account result during `POST /api/claims` registration and `GET /api/claims/{claim_id}/verification`, retaining `MOCK_POLICYCENTER` and `MOCK_BILLINGCENTER` source labels. | It does not submit claims to an external insurer or make automated underwriting decisions. |

## Simulated Business Decisions

- A billing record is `OVERDUE` when `due_date` is before the as-of date and `amount_paid` is less than `amount_due`. A due date equal to the as-of date is not overdue.
- Equipment is considered covered when a matching link exists in `policy_equipment`.
- `run_submission_checks` rejects claim registration (`POST /api/claims`) when any check fails, including an inactive policy, out-of-period incident date, uncovered equipment, or an overdue billing account.
- An eligible claim reaches `UNDER_REVIEW`, `INVESTIGATION_ASSIGNED`, `DECISION_PENDING`, `APPROVED`, or `REJECTED` through explicit actions by authorized staff (`OPS` or `ADMIN`). Document-upload synchronization only moves claims between `UNDER_VERIFICATION` and `DOCUMENTS_REQUIRED`. No automatic approval is made.
- Simulated settlements (`POST /api/claims/{claim_id}/settlement` and `PATCH /api/claims/{claim_id}/settlement`) validate that the claim is `APPROVED`, the payout amount is positive and does not exceed `claim.amount_claimed` or `policy.coverage_limit`, and the currency is supported (`INR` default, plus `USD`, `EUR`, `GBP`). Recording and completing a settlement transitions the claim through `SETTLEMENT_IN_PROGRESS` to `SETTLED` without transferring real money.
- Policy clauses are fictional, paraphrased from a public machinery breakdown policy wording (reference supplied by the developer), and non-binding. They are demo clauses, not the real contract terms of any insurer.
- AI assessments and assistant answers are advisory only. They cite only approved demo clause IDs, and a human officer makes the final decision.

These are prototype rules implemented by this project, not decisions authorized by an insurer.

## Not Yet Implemented

- Live Guidewire PolicyCenter, BillingCenter, and ClaimCenter network integrations.
- Real payment gateway or bank disbursement transfers (all settlement records in `claim_settlements` are simulated).
- The incident report generator (not built).
- Retrieval-augmented generation with vector embeddings over policy text.
- The live Gemini API requires a valid `GEMINI_API_KEY`; offline automated tests use deterministic fake-provider fixtures and do not call the external API.
- Email, SMS, or push notifications outside the in-app notification center.

## Replacing the Mocks

Each adapter is described by a `Protocol` in `backend/app/integrations/base.py`. A real client could implement the same methods and return the shared `IntegrationResult` shape. This describes an extension point only; it does not specify or imply any real integration endpoints.

## Sample Data

The seed script provides illustrative, fictional records: one café business, two equipment items, one policy, one billing record, two claims (`DEMO-000001` closed through the workflow, and `DEMO-000002` in `UNDER_REVIEW`), and fictional policy clauses. They are demo data, not real customer or insurer records.