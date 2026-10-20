import uuid

from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvent
from app.models.enums import ClaimStatus, EventSource, UserRole
from app.workflow.transitions import check_transition


def change_claim_status(
    session: Session,
    claim: Claim,
    target: ClaimStatus,
    actor_role: UserRole,
    actor_user_id: uuid.UUID | None,
    explanation: str,
) -> ClaimEvent:
    current = ClaimStatus(claim.status)
    check_transition(current, target, actor_role)

    event_sources = {
        UserRole.POLICYHOLDER: EventSource.POLICYHOLDER,
        UserRole.OPS: EventSource.OPS,
        UserRole.ADMIN: EventSource.ADMIN,
    }
    try:
        source = event_sources[actor_role]
    except KeyError as exc:
        raise ValueError("Unsupported actor role") from exc

    if not explanation.strip():
        raise ValueError("Explanation is required")

    old_status = claim.status
    claim.status = target.value
    event = ClaimEvent(
        claim_id=claim.id,
        old_status=old_status,
        new_status=target.value,
        source=source.value,
        actor_user_id=actor_user_id,
        explanation=explanation,
    )
    session.add(event)
    session.flush()
    return event