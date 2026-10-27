from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.base import CLAIMCENTER_SOURCE
from app.integrations.mock_claimcenter import MockClaimCenter
from app.integrations.submission_checks import run_submission_checks
from app.models import Claim, ClaimEvent, Equipment, Policy, PolicyEquipment
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


def get_claim_for_user(session: Session, claim_id: uuid.UUID, user: User) -> Claim | None:
    # Staff (OPS, ADMIN) can see any claim.
    # Policyholders are limited to claims for their own business.
    # Returning None for both "missing" and "not yours" means the route
    # responds 404 either way, so existence is not revealed.
    query = select(Claim).where(Claim.id == claim_id)

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
