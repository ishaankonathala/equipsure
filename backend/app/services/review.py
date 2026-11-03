from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingRecord, Claim, ClaimDocument, Policy, PolicyEquipment
from app.models.enums import PolicyStatus


@dataclass(frozen=True)
class RuleCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReviewSummary:
    checks: tuple[RuleCheck, ...]
    suggested_amount: Decimal
    all_passed: bool


def evaluate_claim(session: Session, claim: Claim) -> ReviewSummary:
    policy = session.execute(
        select(Policy).where(Policy.id == claim.policy_id)
    ).scalar_one()
    covered = session.execute(
        select(PolicyEquipment).where(
            PolicyEquipment.policy_id == policy.id,
            PolicyEquipment.equipment_id == claim.equipment_id,
        )
    ).scalar_one_or_none()
    billing = session.execute(
        select(BillingRecord).where(BillingRecord.policy_id == policy.id)
    ).scalars().all()
    present = set(
        session.execute(
            select(ClaimDocument.document_type).where(ClaimDocument.claim_id == claim.id)
        ).scalars().all()
    )

    in_period = (
        policy.status == PolicyStatus.ACTIVE.value
        and policy.start_date <= claim.incident_date <= policy.end_date
    )
    overdue = any(
        record.amount_paid < record.amount_due and record.due_date < date.today()
        for record in billing
    )
    docs_ok = {"INVOICE", "PHOTO"} <= present
    within_limit = claim.amount_claimed <= policy.coverage_limit

    checks = (
        RuleCheck("Policy active on incident date", in_period,
                  f"Period {policy.start_date} to {policy.end_date}"),
        RuleCheck("Equipment covered by policy", covered is not None,
                  "Linked through policy_equipment"),
        RuleCheck("Account not overdue", not overdue,
                  "No unpaid record past its due date"),
        RuleCheck("Required documents present", docs_ok,
                  "INVOICE and PHOTO required"),
        RuleCheck("Claimed amount within coverage limit", within_limit,
                  f"Limit {policy.coverage_limit}"),
    )

    all_passed = all(check.passed for check in checks)
    if covered is None or not in_period:
        suggested = Decimal("0.00")
    else:
        payable = claim.amount_claimed - policy.deductible_amount
        suggested = min(max(payable, Decimal("0.00")), policy.coverage_limit)
        suggested = suggested.quantize(Decimal("0.01"))

    return ReviewSummary(checks=checks, suggested_amount=suggested, all_passed=all_passed)

