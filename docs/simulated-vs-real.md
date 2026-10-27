# Simulated vs Real

## Purpose

EquipSure is a college project that simulates equipment-breakdown insurance claims. It does not connect to a real insurer or a real Guidewire environment, and its seeded demo records are fictional rather than real customer data.

## Real and Implemented

| Area | What runs in this codebase |
|---|---|
| Authentication | Bcrypt password hashing and JWT login are implemented in `backend/app/core/security.py` and `backend/app/api/routes/auth.py`. |
| Authorization | Role checks and business-scoped claim access are implemented in `backend/app/core/deps.py` and `backend/app/services/claims.py`. |
| Database schema | PostgreSQL models and Alembic migrations `0001` through `0005` define the implemented schema. |
| Claim workflow | `backend/app/workflow/transitions.py` and `backend/app/workflow/service.py` implement allowed status changes and append-only audit events in `claim_events`; a database trigger rejects event updates and deletes. |
| Documents | Uploads are checked against file signatures and a configured size limit in `backend/app/services/documents.py`; `backend/app/services/document_storage.py` stores files privately under the configured `STORAGE_DIR` on local disk. |
| Messages and notifications | Authenticated claim messages and user-scoped in-app notifications are persisted and served by the API. Notification status changes use `PATCH`. These are not email or real-time delivery. |
| Policy assistant | A keyword-retrieval assistant over the approved demo clauses (`backend/app/services/assistant_retrieval.py`, `backend/app/services/assistant.py`). It cites only retrieved clause IDs and refuses when nothing matches. It is not retrieval-augmented generation with embeddings. |
| AI assessment | Document classification and claim assessment are validated against approved clause IDs and must be advisory. In fake mode (the default), assessment and assistant answers are fixed, reviewed, simulated responses from `backend/app/ai/canned_responses.py`, not model output. Gemini is wired and optional, but it was unavailable during testing (high demand, HTTP 503), so live AI is not demonstrated. Only synthetic documents should ever be sent to it. |
| Frontend (React, TypeScript) | Sign-in and sign-out, claim lookup, document checklist and upload, OPS-only claim status changes limited to legal moves, OPS-only advisory assessment, notifications with mark-as-read, and the policy assistant panel. The access token is kept in memory only. |

## Simulated Guidewire-Aligned Adapters

| Area | Mock module | What it does | What it does NOT do |
|---|---|---|---|
| PolicyCenter | `backend/app/integrations/mock_policycenter.py` | Reads local policy data, checks policy validity and checks whether equipment is linked through `policy_equipment`. Source label: `MOCK_POLICYCENTER`. | It does not contact Guidewire or verify coverage with a real insurer. |
| BillingCenter | `backend/app/integrations/mock_billingcenter.py` | Reads local billing records and computes effective account and record statuses for an as-of date. Source label: `MOCK_BILLINGCENTER`. | It does not process payments or contact a billing system. |
| ClaimCenter | `backend/app/integrations/mock_claimcenter.py` | Checks whether a claim reference already exists and reads local claim status history. Source label: `MOCK_CLAIMCENTER`. | `register_claim` does not create a claim and no external claim system is contacted. |
| Combined submission checks | `backend/app/integrations/submission_checks.py` | Combines PolicyCenter validity and equipment results with the BillingCenter account result; its results retain the `MOCK_POLICYCENTER` and `MOCK_BILLINGCENTER` source labels. | It does not create or change a claim, submit it to an insurer, or make an insurance decision. |

## Simulated Business Decisions

- A billing record is `OVERDUE` when `due_date` is before the as-of date and `amount_paid` is less than `amount_due`. A due date equal to the as-of date is not overdue.
- Equipment is considered covered when a matching link exists in `policy_equipment`.
- `run_submission_checks` rejects its result when any check fails, including an overdue account. It returns a decision result only; there is no flag state or claim submission route in this flow.
- An eligible claim reaches `UNDER_REVIEW` through an explicit status change by authorized staff (OPS or ADMIN). Document-upload synchronization does not move it to `UNDER_REVIEW`. No automatic approval or insurer decision is made.
- `register_claim` only checks reference uniqueness; it does not create claims.
- Policy clauses are fictional, paraphrased from a public machinery breakdown policy wording (reference supplied by the developer), and non-binding. They are demo clauses, not the real contract terms of any insurer.
- AI assessments and assistant answers are advisory only. They cite only approved demo clause IDs, and a human makes the final decision.

These are prototype rules implemented by this project, not decisions authorized by an insurer.

## Not Yet Implemented

- A user-interface screen for claim messages. Messages are implemented and tested in the API.
- The incident report generator (not built).
- Retrieval-augmented generation with embeddings over policy text.
- Live model output for the assessment and policy assistant. The code path exists and is tested offline; it has not been shown working against the Gemini API.
- Real Guidewire integration, payments, and real insurer decisions.
- Email or real-time notifications, automatic approval, and a real claim-submission route.

## Replacing the Mocks

Each adapter is described by a `Protocol` in `backend/app/integrations/base.py`. A real client could implement the same methods and return the shared `IntegrationResult` shape. This describes an extension point only; it does not specify or imply any real integration endpoints.

## Sample Data

The seed script provides illustrative, fictional records: one café business, two equipment items, one policy, one billing record, two claims (`DEMO-000001` closed through the workflow, and `DEMO-000002` in `UNDER_REVIEW`), and fictional policy clauses. They are demo data, not real customer or insurer records.