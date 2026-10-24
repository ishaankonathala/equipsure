import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.integrations.base import IntegrationResult
from app.integrations.mock_billingcenter import MockBillingCenter
from app.integrations.mock_policycenter import MockPolicyCenter


@dataclass(frozen=True)
class SubmissionDecision:
    accepted: bool
    failures: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    results: tuple[IntegrationResult, ...] = ()


def run_submission_checks(
    session: Session,
    policy_number: str,
    equipment_id: uuid.UUID,
    incident_date: date,
    on_date: date,
) -> SubmissionDecision:
    policy = MockPolicyCenter(session)
    validity_result = policy.check_validity(policy_number, incident_date)
    equipment_result = policy.is_equipment_covered(policy_number, equipment_id)

    billing = MockBillingCenter(session)
    billing_result = billing.get_account_status(policy_number, on_date)

    results = (validity_result, equipment_result, billing_result)
    failures = [result.reason for result in results if not result.ok and result.reason]
    if (
        billing_result.ok
        and billing_result.data.get("account_status") == "OVERDUE"
        and "Policy account is overdue" not in failures
    ):
        failures.append("Policy account is overdue")

    return SubmissionDecision(
        accepted=not failures,
        failures=tuple(failures),
        sources=tuple(result.source for result in results),
        results=results,
    )