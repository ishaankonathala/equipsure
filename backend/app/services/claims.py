from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.base import (
    BILLINGCENTER_SOURCE,
    CLAIMCENTER_SOURCE,
    POLICYCENTER_SOURCE,
)
from app.integrations.mock_claimcenter import MockClaimCenter
from app.integrations.submission_checks import run_submission_checks
from app.models import Claim, ClaimDocument, ClaimEvent, Equipment, Policy, PolicyEquipment
from app.models.enums import ClaimStatus, EventSource, UserRole
from app.models.user import User

MAX_CLAIM_AMOUNT = Decimal("9999999999.99")
MAX_DESCRIPTION_LENGTH = 2000


class ClaimRegistrationError(Exception):
    """Raised when a claim registration request fails validation or eligibility checks."""

    def __init__(
        self,
        detail: str,
        *,
        failures: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.failures = failures or (detail,)
        self.sources = sources


@dataclass(frozen=True)
class RegisteredClaimResult:
    claim: Claim
    event: ClaimEvent
    sources: tuple[str, ...]


def get_claim_for_user(
    session: Session, claim_id: uuid.UUID | str, user: User
) -> Claim | None:
    # Staff (OPS, ADMIN) can see any claim.
    # Policyholders are limited to claims for their own business.
    # Returning None for both "missing" and "not yours" means the route
    # responds 404 either way, so existence is not revealed.
    parsed_uuid: uuid.UUID | None = None
    if isinstance(claim_id, uuid.UUID):
        parsed_uuid = claim_id
    else:
        raw = str(claim_id).strip()
        if not raw:
            return None
        try:
            parsed_uuid = uuid.UUID(raw)
        except ValueError:
            parsed_uuid = None

    if parsed_uuid is not None:
        query = select(Claim).where(Claim.id == parsed_uuid)
    else:
        query = select(Claim).where(Claim.reference == str(claim_id).strip())

    if user.role == "POLICYHOLDER":
        query = query.where(Claim.business_id == user.business_id)

    return session.execute(query).scalar_one_or_none()


def generate_claim_reference(session: Session) -> str:
    """Generate a unique claim reference verified via MockClaimCenter."""
    claim_center = MockClaimCenter(session)
    base_number = (
        session.execute(select(func.count()).select_from(Claim)).scalar_one() + 1
    )

    for offset in range(50):
        candidate = f"CLM-{base_number + offset:06d}"
        check = claim_center.register_claim(candidate)
        if check.ok:
            return check.data["reference"]

    for _ in range(20):
        candidate = f"CLM-{secrets.token_hex(4).upper()}"
        check = claim_center.register_claim(candidate)
        if check.ok:
            return check.data["reference"]

    raise ClaimRegistrationError(
        "Could not allocate a unique claim reference",
        sources=(CLAIMCENTER_SOURCE,),
    )


def list_registration_options(session: Session, user: User) -> dict:
    """Return policies and covered equipment belonging to the policyholder's business."""
    if user.role != UserRole.POLICYHOLDER.value or user.business_id is None:
        raise PermissionError("Only policyholders have registration options")

    policies = (
        session.execute(
            select(Policy)
            .where(Policy.business_id == user.business_id)
            .order_by(Policy.policy_number.asc())
        )
        .scalars()
        .all()
    )
    equipment_items = (
        session.execute(
            select(Equipment)
            .where(Equipment.business_id == user.business_id)
            .order_by(Equipment.description.asc(), Equipment.id.asc())
        )
        .scalars()
        .all()
    )
    links = (
        session.execute(
            select(PolicyEquipment).where(
                PolicyEquipment.policy_id.in_([p.id for p in policies])
            )
        )
        .scalars()
        .all()
        if policies
        else []
    )
    covered_by_policy: dict[uuid.UUID, list[str]] = {p.id: [] for p in policies}
    for link in links:
        if link.policy_id in covered_by_policy:
            covered_by_policy[link.policy_id].append(str(link.equipment_id))

    return {
        "policies": [
            {
                "id": str(policy.id),
                "policy_number": policy.policy_number,
                "status": policy.status,
                "start_date": policy.start_date.isoformat(),
                "end_date": policy.end_date.isoformat(),
                "coverage_limit": str(policy.coverage_limit),
                "deductible_amount": str(policy.deductible_amount),
                "covered_equipment_ids": covered_by_policy.get(policy.id, []),
            }
            for policy in policies
        ],
        "equipment": [
            {
                "id": str(item.id),
                "category": item.category,
                "description": item.description,
            }
            for item in equipment_items
        ],
    }


def register_claim_for_user(
    session: Session,
    user: User,
    *,
    policy_number: str,
    equipment_id: uuid.UUID,
    incident_date: date,
    incident_description: str,
    amount_claimed: Decimal,
    on_date: date | None = None,
    reference: str | None = None,
) -> RegisteredClaimResult:
    """Register a new claim for a policyholder after running mock Guidewire checks."""
    if user.role != UserRole.POLICYHOLDER.value or user.business_id is None:
        raise PermissionError("Only policyholders may register claims")

    normalized_policy = policy_number.strip()
    if not normalized_policy:
        raise ClaimRegistrationError("Policy number is required")

    trimmed_description = incident_description.strip()
    if not trimmed_description:
        raise ClaimRegistrationError("Incident description is required")
    if len(trimmed_description) > MAX_DESCRIPTION_LENGTH:
        raise ClaimRegistrationError(
            f"Incident description exceeds {MAX_DESCRIPTION_LENGTH} characters"
        )

    if amount_claimed <= Decimal("0"):
        raise ClaimRegistrationError("Amount claimed must be greater than zero")
    if amount_claimed > MAX_CLAIM_AMOUNT:
        raise ClaimRegistrationError("Amount claimed exceeds maximum allowed limit")

    # Enforce tenant isolation before and alongside submission checks so a
    # policyholder cannot register claims against another business's policy/equipment.
    policy = session.execute(
        select(Policy).where(
            Policy.policy_number == normalized_policy,
            Policy.business_id == user.business_id,
        )
    ).scalar_one_or_none()
    if policy is None:
        raise ClaimRegistrationError(
            "Policy not found",
            failures=("Policy not found",),
            sources=("MOCK_POLICYCENTER",),
        )

    equipment = session.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.business_id == user.business_id,
        )
    ).scalar_one_or_none()

    effective_on_date = on_date if on_date is not None else incident_date
    decision = run_submission_checks(
        session,
        normalized_policy,
        equipment_id,
        incident_date,
        effective_on_date,
    )
    if not decision.accepted or equipment is None:
        failures = list(decision.failures)
        if equipment is None and "Equipment is not covered by this policy" not in failures:
            failures.append("Equipment is not covered by this policy")
        raise ClaimRegistrationError(
            "; ".join(failures),
            failures=tuple(failures),
            sources=decision.sources,
        )

    claim_center = MockClaimCenter(session)
    if reference is not None:
        ref_check = claim_center.register_claim(reference)
        if not ref_check.ok:
            raise ClaimRegistrationError(
                ref_check.reason or "Invalid claim reference",
                failures=(ref_check.reason or "Invalid claim reference",),
                sources=(claim_center.source,),
            )
        chosen_reference = ref_check.data["reference"]
    else:
        chosen_reference = generate_claim_reference(session)

    quantized_amount = amount_claimed.quantize(Decimal("0.01"))
    claim = Claim(
        id=uuid.uuid4(),
        reference=chosen_reference,
        business_id=user.business_id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status=ClaimStatus.SUBMITTED.value,
        incident_date=incident_date,
        incident_description=trimmed_description,
        amount_claimed=quantized_amount,
    )
    try:
        with session.begin_nested():
            session.add(claim)
            session.flush()
            event = ClaimEvent(
                claim_id=claim.id,
                old_status=None,
                new_status=ClaimStatus.SUBMITTED.value,
                source=EventSource.POLICYHOLDER.value,
                actor_user_id=user.id,
                explanation="Claim submitted by policyholder.",
            )
            session.add(event)
            session.flush()
    except IntegrityError as exc:
        raise ClaimRegistrationError(
            "Claim reference already exists",
            failures=("Claim reference already exists",),
            sources=(claim_center.source,),
        ) from exc

    return RegisteredClaimResult(
        claim=claim,
        event=event,
        sources=(*decision.sources, claim_center.source),
    )


def verify_claim_for_user(
    session: Session,
    claim_id: uuid.UUID | str,
    user: User,
) -> dict | None:
    """Run read-only simulated PolicyCenter and BillingCenter verification for a claim."""
    claim = get_claim_for_user(session, claim_id, user)
    if claim is None:
        return None

    policy = session.execute(
        select(Policy).where(
            Policy.id == claim.policy_id,
            Policy.business_id == claim.business_id,
        )
    ).scalar_one_or_none()

    equipment = session.execute(
        select(Equipment).where(
            Equipment.id == claim.equipment_id,
            Equipment.business_id == claim.business_id,
        )
    ).scalar_one_or_none()

    policy_number = policy.policy_number if policy is not None else ""
    decision = run_submission_checks(
        session,
        policy_number,
        claim.equipment_id,
        claim.incident_date,
        claim.incident_date,
    )
    validity_result, equipment_result, billing_result = decision.results

    equipment_covered = bool(
        policy is not None and equipment is not None and equipment_result.ok
    )
    is_active = bool(policy is not None and policy.status == "ACTIVE")
    incident_date_within_period = bool(
        policy is not None
        and policy.start_date <= claim.incident_date <= policy.end_date
    )

    policy_reasons: list[str] = []
    if not validity_result.ok and validity_result.reason:
        policy_reasons.append(validity_result.reason)
    if not equipment_covered:
        eq_reason = (
            equipment_result.reason
            if not equipment_result.ok and equipment_result.reason
            else "Equipment is not covered by this policy"
        )
        if eq_reason not in policy_reasons:
            policy_reasons.append(eq_reason)

    billing_reasons: list[str] = []
    if not billing_result.ok and billing_result.reason:
        billing_reasons.append(billing_result.reason)
    elif billing_result.ok and billing_result.data.get("account_status") == "OVERDUE":
        billing_reasons.append("Policy account is overdue")

    failures: list[str] = list(decision.failures)
    if (
        not equipment_covered
        and "Equipment is not covered by this policy" not in failures
        and "Policy not found" not in failures
    ):
        failures.append("Equipment is not covered by this policy")

    policy_passed = bool(
        policy is not None and validity_result.ok and equipment_covered
    )
    billing_passed = bool(
        policy is not None
        and billing_result.ok
        and billing_result.data.get("account_status") != "OVERDUE"
    )
    overall_passed = bool(policy_passed and billing_passed)

    return {
        "claim_id": str(claim.id),
        "claim_reference": claim.reference,
        "incident_date": claim.incident_date.isoformat(),
        "simulated": True,
        "simulation_notice": (
            "Simulated local Guidewire-aligned verification "
            "(MOCK_POLICYCENTER, MOCK_BILLINGCENTER)."
        ),
        "overall_passed": overall_passed,
        "sources": [POLICYCENTER_SOURCE, BILLINGCENTER_SOURCE],
        "failures": failures,
        "policy_verification": {
            "source": POLICYCENTER_SOURCE,
            "simulated": True,
            "passed": policy_passed,
            "policy_id": str(claim.policy_id),
            "policy_number": policy.policy_number if policy is not None else None,
            "status": policy.status if policy is not None else None,
            "is_active": is_active,
            "start_date": (
                policy.start_date.isoformat() if policy is not None else None
            ),
            "end_date": policy.end_date.isoformat() if policy is not None else None,
            "incident_date_within_period": incident_date_within_period,
            "equipment_id": str(claim.equipment_id),
            "equipment_description": (
                equipment.description if equipment is not None else None
            ),
            "equipment_category": (
                equipment.category if equipment is not None else None
            ),
            "equipment_covered": equipment_covered,
            "coverage_limit": (
                str(policy.coverage_limit) if policy is not None else None
            ),
            "deductible_amount": (
                str(policy.deductible_amount) if policy is not None else None
            ),
            "reasons": policy_reasons,
        },
        "billing_verification": {
            "source": BILLINGCENTER_SOURCE,
            "simulated": True,
            "passed": billing_passed,
            "account_status": (
                billing_result.data.get("account_status")
                if policy is not None and billing_result.ok
                else None
            ),
            "business_rule_result": "ELIGIBLE" if billing_passed else "INELIGIBLE",
            "as_of": claim.incident_date.isoformat(),
            "premium_amount": (
                str(policy.premium_amount) if policy is not None else None
            ),
            "record_count": (
                len(billing_result.data.get("records", []))
                if policy is not None and billing_result.ok
                else 0
            ),
            "reasons": billing_reasons,
        },
    }


def list_claim_history_for_user(
    session: Session,
    claim_id: uuid.UUID | str,
    user: User,
) -> list[dict] | None:
    """Return chronological status history events for a claim visible to the user."""
    claim = get_claim_for_user(session, claim_id, user)
    if claim is None:
        return None

    events = (
        session.execute(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.created_at.asc(), ClaimEvent.id.asc())
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": event.id,
            "claim_id": str(event.claim_id),
            "old_status": event.old_status,
            "new_status": event.new_status,
            "source": event.source,
            "actor_user_id": (
                str(event.actor_user_id) if event.actor_user_id is not None else None
            ),
            "is_system": event.source == EventSource.SYSTEM.value,
            "explanation": event.explanation,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


def list_claim_documents_for_user(
    session: Session,
    claim_id: uuid.UUID | str,
    user: User,
) -> list[dict] | None:
    """Return safe document metadata for a claim visible to the user."""
    claim = get_claim_for_user(session, claim_id, user)
    if claim is None:
        return None

    documents = (
        session.execute(
            select(ClaimDocument)
            .where(ClaimDocument.claim_id == claim.id)
            .order_by(ClaimDocument.uploaded_at.asc(), ClaimDocument.id.asc())
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(doc.id),
            "claim_id": str(doc.claim_id),
            "document_type": doc.document_type,
            "original_filename": doc.original_filename,
            "content_type": doc.content_type,
            "size_bytes": doc.size_bytes,
            "uploaded_at": doc.uploaded_at.isoformat(),
        }
        for doc in documents
    ]
