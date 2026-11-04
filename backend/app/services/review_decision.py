from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Claim
from app.models.enums import ClaimStatus, UserRole
from app.services.review import evaluate_claim
from app.workflow.service import change_claim_status
from app.workflow.transitions import TransitionError


class ReviewDecisionError(Exception):
    """Raised when an officer review decision cannot be processed."""


def decide_claim(
    session: Session,
    claim: Claim,
    actor: Any,
    decision: str,
    approved_amount: Decimal | None,
    reason: str | None,
) -> tuple[str, str]:
    if not decision or not isinstance(decision, str):
        raise ReviewDecisionError("Unknown decision")
    normalized_decision = decision.strip().upper()
    if normalized_decision not in {"APPROVE", "REJECT"}:
        raise ReviewDecisionError("Unknown decision")

    summary = evaluate_claim(session, claim)

    if normalized_decision == "REJECT":
        if reason is None or not reason.strip():
            raise ReviewDecisionError("A reason is required to reject")
        target = ClaimStatus.REJECTED
        explanation = "Rejected by officer. Reason: " + reason.strip()
    else:
        if approved_amount is None:
            raise ReviewDecisionError("An approved amount is required")
        if approved_amount < 0 or approved_amount > claim.amount_claimed:
            raise ReviewDecisionError(
                "Approved amount must be between 0 and the claimed amount"
            )
        if approved_amount != summary.suggested_amount:
            if reason is None or not reason.strip():
                raise ReviewDecisionError(
                    "A reason is required when the amount differs from the suggestion"
                )
        target = ClaimStatus.APPROVED
        explanation = f"Approved by officer. Suggested {summary.suggested_amount}, approved {approved_amount}."
        if reason is not None and reason.strip():
            explanation += " Reason: " + reason.strip()

    try:
        actor_role = UserRole(actor.role)
        change_claim_status(
            session,
            claim,
            target,
            actor_role,
            actor.id,
            explanation,
        )
    except TransitionError as exc:
        raise ReviewDecisionError(str(exc)) from None

    return (target.value, explanation)

