import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvent, User
from app.models.enums import ClaimStatus, EventSource, UserRole
from app.services.checklist import missing_required_documents
from app.workflow.transitions import check_transition

SYSTEM_ACTOR_ROLE = "SYSTEM"


def change_claim_status(
    session: Session,
    claim: Claim,
    target: ClaimStatus,
    actor_role: UserRole | str,
    actor_user_id: uuid.UUID | None,
    explanation: str,
) -> ClaimEvent:
    current = ClaimStatus(claim.status)
    check_transition(current, target, actor_role)

    event_sources = {
        UserRole.POLICYHOLDER: EventSource.POLICYHOLDER,
        UserRole.OPS: EventSource.OPS,
        UserRole.ADMIN: EventSource.ADMIN,
        SYSTEM_ACTOR_ROLE: EventSource.SYSTEM,
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

    from app.services.messaging import create_notification

    policyholder = session.execute(
        select(User)
        .where(
            User.business_id == claim.business_id,
            User.role == UserRole.POLICYHOLDER.value,
            User.is_active.is_(True),
        )
        .order_by(User.id)
        .limit(1)
    ).scalar_one_or_none()
    if policyholder is not None:
        create_notification(
            session,
            policyholder.id,
            claim.id,
            "CLAIM_STATUS_CHANGED",
            f"Claim {claim.reference} is now {target.value.replace('_', ' ').title()}.",
        )

    return event


def sync_documents_status(
    session: Session, claim: Claim, present_types: set[str]
) -> ClaimEvent | None:
    missing = missing_required_documents(present_types)

    if claim.status == "SUBMITTED":
        return None
    if missing and claim.status == "UNDER_VERIFICATION":
        return change_claim_status(
            session,
            claim,
            ClaimStatus.DOCUMENTS_REQUIRED,
            SYSTEM_ACTOR_ROLE,
            None,
            "Required documents missing: " + ", ".join(missing),
        )
    if not missing and claim.status == "DOCUMENTS_REQUIRED":
        return change_claim_status(
            session,
            claim,
            ClaimStatus.UNDER_VERIFICATION,
            SYSTEM_ACTOR_ROLE,
            None,
            "Required documents received",
        )
    if not missing and claim.status == "DOCUMENTS_REQUIRED":
        return change_claim_status(
            session,
            claim,
            ClaimStatus.UNDER_VERIFICATION,
            SYSTEM_ACTOR_ROLE,
            None,
            "Required documents received",
        )
    return None