from dataclasses import dataclass
from datetime import date, datetime, timezone
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
from app.models import (
    Claim,
    ClaimDocument,
    ClaimEvent,
    ClaimSettlement,
    Equipment,
    Policy,
    PolicyEquipment,
)
from app.models.enums import (
    ClaimStatus,
    EventSource,
    SettlementCurrency,
    SettlementStatus,
    UserRole,
)
from app.models.user import User
from app.workflow.service import change_claim_status

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


TERMINAL_OR_POST_DECISION_ASSIGNMENT_STATUSES = {
    ClaimStatus.APPROVED.value,
    ClaimStatus.REJECTED.value,
    ClaimStatus.SETTLEMENT_IN_PROGRESS.value,
    ClaimStatus.SETTLED.value,
    ClaimStatus.CLOSED.value,
    ClaimStatus.WITHDRAWN.value,
}


def get_rejection_reason(session: Session, claim: Claim) -> str | None:
    """Return the recorded rejection explanation from claim_events if the claim was rejected."""
    if claim.status not in {ClaimStatus.REJECTED.value, ClaimStatus.CLOSED.value}:
        return None

    event = (
        session.execute(
            select(ClaimEvent)
            .where(
                ClaimEvent.claim_id == claim.id,
                ClaimEvent.new_status == ClaimStatus.REJECTED.value,
            )
            .order_by(ClaimEvent.created_at.desc(), ClaimEvent.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return event.explanation if event is not None else None


def get_assigned_officer_summary(session: Session, claim: Claim) -> dict:
    """Return assigned officer fields for a claim."""
    if claim.assigned_officer_id is None:
        return {
            "assigned_officer_id": None,
            "assigned_officer_name": None,
            "assigned_officer_role": None,
            "assigned_at": None,
        }

    officer = session.execute(
        select(User).where(User.id == claim.assigned_officer_id)
    ).scalar_one_or_none()
    return {
        "assigned_officer_id": str(claim.assigned_officer_id),
        "assigned_officer_name": officer.full_name if officer is not None else None,
        "assigned_officer_role": officer.role if officer is not None else None,
        "assigned_at": (
            claim.assigned_at.isoformat() if claim.assigned_at is not None else None
        ),
    }


def list_assignable_officers(session: Session, user: User) -> list[dict]:
    """Return active OPS and ADMIN officers available for claim assignment."""
    if user.role not in {UserRole.OPS.value, UserRole.ADMIN.value}:
        raise PermissionError(
            "Only officers and administrators may list assignable officers"
        )

    officers = (
        session.execute(
            select(User)
            .where(
                User.role.in_([UserRole.OPS.value, UserRole.ADMIN.value]),
                User.is_active.is_(True),
            )
            .order_by(User.full_name.asc(), User.email.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(officer.id),
            "email": officer.email,
            "full_name": officer.full_name,
            "role": officer.role,
        }
        for officer in officers
    ]


def assign_officer_to_claim(
    session: Session,
    claim: Claim,
    actor: User,
    *,
    officer_user_id: uuid.UUID,
    notes: str | None = None,
    move_to_investigation: bool = True,
) -> dict:
    """Assign an active OPS/ADMIN officer to a claim and record an audit event."""
    if actor.role not in {UserRole.OPS.value, UserRole.ADMIN.value}:
        raise PermissionError("Only officers and administrators may assign claims")

    if claim.status in TERMINAL_OR_POST_DECISION_ASSIGNMENT_STATUSES:
        raise ValueError(
            f"Cannot assign officer to a claim in {claim.status} status"
        )

    assignee = session.execute(
        select(User).where(User.id == officer_user_id)
    ).scalar_one_or_none()
    if (
        assignee is None
        or not assignee.is_active
        or assignee.role not in {UserRole.OPS.value, UserRole.ADMIN.value}
    ):
        raise ValueError("Assigned user must be an active OPS or ADMIN officer")

    trimmed_notes = (notes or "").strip()
    if len(trimmed_notes) > 500:
        raise ValueError("Assignment notes cannot exceed 500 characters")

    now = datetime.now(timezone.utc)
    claim.assigned_officer_id = assignee.id
    claim.assigned_at = now
    claim.updated_at = now

    base_explanation = (
        f"Assigned officer {assignee.full_name} ({assignee.role})."
    )
    explanation = (
        f"{base_explanation} Note: {trimmed_notes}"
        if trimmed_notes
        else base_explanation
    )

    if claim.status == ClaimStatus.UNDER_REVIEW.value and move_to_investigation:
        event = change_claim_status(
            session,
            claim,
            ClaimStatus.INVESTIGATION_ASSIGNED,
            UserRole(actor.role),
            actor.id,
            explanation,
        )
    else:
        event = ClaimEvent(
            claim_id=claim.id,
            old_status=claim.status,
            new_status=claim.status,
            source=actor.role,
            actor_user_id=actor.id,
            explanation=explanation,
        )
        session.add(event)
        session.flush()

    return {
        "claim_id": str(claim.id),
        "reference": claim.reference,
        "status": claim.status,
        "assigned_officer_id": str(assignee.id),
        "assigned_officer_name": assignee.full_name,
        "assigned_officer_role": assignee.role,
        "assigned_at": claim.assigned_at.isoformat(),
        "event_id": event.id,
    }


def generate_settlement_reference(session: Session) -> str:
    """Generate a unique simulated settlement reference (STL-XXXXXX)."""
    base_number = (
        session.execute(select(func.count()).select_from(ClaimSettlement)).scalar_one()
        + 1
    )
    for offset in range(50):
        candidate = f"STL-{base_number + offset:06d}"
        exists = session.execute(
            select(ClaimSettlement.id).where(
                ClaimSettlement.settlement_reference == candidate
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate

    for _ in range(20):
        candidate = f"STL-{secrets.token_hex(4).upper()}"
        exists = session.execute(
            select(ClaimSettlement.id).where(
                ClaimSettlement.settlement_reference == candidate
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate

    raise ValueError("Could not allocate a unique settlement reference")


def _serialize_settlement(settlement: ClaimSettlement) -> dict:
    return {
        "id": str(settlement.id),
        "claim_id": str(settlement.claim_id),
        "settlement_reference": settlement.settlement_reference,
        "amount": str(settlement.amount),
        "currency": settlement.currency,
        "status": settlement.status,
        "notes": settlement.notes,
        "created_by_user_id": str(settlement.created_by_user_id),
        "settled_at": (
            settlement.settled_at.isoformat()
            if settlement.settled_at is not None
            else None
        ),
        "created_at": settlement.created_at.isoformat(),
        "updated_at": settlement.updated_at.isoformat(),
        "source": CLAIMCENTER_SOURCE,
        "simulated": True,
    }


def _settlement_envelope(claim: Claim, settlement: ClaimSettlement | None) -> dict:
    return {
        "claim_id": str(claim.id),
        "claim_reference": claim.reference,
        "claim_status": claim.status,
        "simulated": True,
        "simulation_notice": (
            "Simulated local Guidewire ClaimCenter settlement tracking "
            "(MOCK_CLAIMCENTER). No real payment or external transfer is executed."
        ),
        "supported_currencies": [c.value for c in SettlementCurrency],
        "default_currency": SettlementCurrency.INR.value,
        "settlement": (
            _serialize_settlement(settlement) if settlement is not None else None
        ),
    }


def get_settlement_for_user(
    session: Session,
    claim_id: uuid.UUID | str,
    user: User,
) -> dict | None:
    """Return simulated settlement tracking details for a claim visible to the user."""
    claim = get_claim_for_user(session, claim_id, user)
    if claim is None:
        return None

    settlement = session.execute(
        select(ClaimSettlement).where(ClaimSettlement.claim_id == claim.id)
    ).scalar_one_or_none()
    return _settlement_envelope(claim, settlement)


def record_claim_settlement(
    session: Session,
    claim: Claim,
    actor: User,
    *,
    amount: Decimal,
    currency: str = SettlementCurrency.INR.value,
    notes: str | None = None,
    mark_settled: bool = False,
    settlement_reference: str | None = None,
) -> dict:
    """Record a simulated settlement for an APPROVED claim and append audit events."""
    if actor.role not in {UserRole.OPS.value, UserRole.ADMIN.value}:
        raise PermissionError(
            "Only officers and administrators may record settlements"
        )

    existing = session.execute(
        select(ClaimSettlement).where(ClaimSettlement.claim_id == claim.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("A settlement record already exists for this claim")

    if claim.status not in {
        ClaimStatus.APPROVED.value,
        ClaimStatus.SETTLEMENT_IN_PROGRESS.value,
    }:
        raise ValueError(
            f"Cannot record settlement for a claim in {claim.status} status; "
            "claim must be APPROVED"
        )

    normalized_currency = (currency or "").strip().upper()
    allowed_currencies = {c.value for c in SettlementCurrency}
    if normalized_currency not in allowed_currencies:
        raise ValueError(
            f"Unsupported settlement currency '{currency}'. "
            f"Supported currencies: {', '.join(sorted(allowed_currencies))}"
        )

    if amount <= Decimal("0"):
        raise ValueError("Settlement amount must be greater than zero")
    if amount > MAX_CLAIM_AMOUNT:
        raise ValueError("Settlement amount exceeds maximum allowed limit")
    if amount > claim.amount_claimed:
        raise ValueError(
            f"Settlement amount cannot exceed claimed amount ({claim.amount_claimed})"
        )

    policy = session.execute(
        select(Policy).where(
            Policy.id == claim.policy_id,
            Policy.business_id == claim.business_id,
        )
    ).scalar_one_or_none()
    if policy is not None and amount > policy.coverage_limit:
        raise ValueError(
            f"Settlement amount cannot exceed policy coverage limit ({policy.coverage_limit})"
        )

    trimmed_notes = (notes or "").strip() or None
    if trimmed_notes is not None and len(trimmed_notes) > 1000:
        raise ValueError("Settlement notes cannot exceed 1000 characters")

    if settlement_reference is not None:
        chosen_ref = settlement_reference.strip()
        if not chosen_ref:
            raise ValueError("Settlement reference cannot be blank")
    else:
        chosen_ref = generate_settlement_reference(session)

    quantized_amount = amount.quantize(Decimal("0.01"))
    now = datetime.now(timezone.utc)
    target_settlement_status = (
        SettlementStatus.SETTLED.value
        if mark_settled
        else SettlementStatus.IN_PROGRESS.value
    )
    settled_at = now if mark_settled else None

    settlement = ClaimSettlement(
        id=uuid.uuid4(),
        claim_id=claim.id,
        settlement_reference=chosen_ref,
        amount=quantized_amount,
        currency=normalized_currency,
        status=target_settlement_status,
        notes=trimmed_notes,
        created_by_user_id=actor.id,
        settled_at=settled_at,
        created_at=now,
        updated_at=now,
    )

    try:
        with session.begin_nested():
            session.add(settlement)
            session.flush()

            note_suffix = f" Note: {trimmed_notes}" if trimmed_notes else ""
            if claim.status == ClaimStatus.APPROVED.value:
                change_claim_status(
                    session,
                    claim,
                    ClaimStatus.SETTLEMENT_IN_PROGRESS,
                    UserRole(actor.role),
                    actor.id,
                    (
                        f"Simulated settlement {chosen_ref} initiated for "
                        f"{normalized_currency} {quantized_amount}.{note_suffix}"
                    ),
                )
                if mark_settled:
                    change_claim_status(
                        session,
                        claim,
                        ClaimStatus.SETTLED,
                        UserRole(actor.role),
                        actor.id,
                        (
                            f"Simulated settlement {chosen_ref} completed for "
                            f"{normalized_currency} {quantized_amount}.{note_suffix}"
                        ),
                    )
            else:
                if mark_settled:
                    change_claim_status(
                        session,
                        claim,
                        ClaimStatus.SETTLED,
                        UserRole(actor.role),
                        actor.id,
                        (
                            f"Simulated settlement {chosen_ref} completed for "
                            f"{normalized_currency} {quantized_amount}.{note_suffix}"
                        ),
                    )
                else:
                    event = ClaimEvent(
                        claim_id=claim.id,
                        old_status=claim.status,
                        new_status=claim.status,
                        source=actor.role,
                        actor_user_id=actor.id,
                        explanation=(
                            f"Simulated settlement {chosen_ref} recorded for "
                            f"{normalized_currency} {quantized_amount}.{note_suffix}"
                        ),
                    )
                    session.add(event)
                    session.flush()
    except IntegrityError as exc:
        raise ValueError(
            "A settlement record or reference already exists for this claim"
        ) from exc

    return _settlement_envelope(claim, settlement)


def complete_claim_settlement(
    session: Session,
    claim: Claim,
    actor: User,
    *,
    notes: str | None = None,
) -> dict:
    """Mark an IN_PROGRESS simulated settlement as SETTLED and advance the claim."""
    if actor.role not in {UserRole.OPS.value, UserRole.ADMIN.value}:
        raise PermissionError(
            "Only officers and administrators may complete settlements"
        )

    settlement = session.execute(
        select(ClaimSettlement).where(ClaimSettlement.claim_id == claim.id)
    ).scalar_one_or_none()
    if settlement is None:
        raise LookupError("Settlement record not found for this claim")

    if settlement.status == SettlementStatus.SETTLED.value:
        raise ValueError("Settlement is already marked as SETTLED")

    if claim.status != ClaimStatus.SETTLEMENT_IN_PROGRESS.value:
        raise ValueError(
            f"Cannot complete settlement when claim is in {claim.status} status"
        )

    trimmed_notes = (notes or "").strip() or None
    if trimmed_notes is not None and len(trimmed_notes) > 1000:
        raise ValueError("Settlement notes cannot exceed 1000 characters")

    now = datetime.now(timezone.utc)
    settlement.status = SettlementStatus.SETTLED.value
    settlement.settled_at = now
    settlement.updated_at = now
    if trimmed_notes is not None:
        settlement.notes = trimmed_notes

    note_suffix = f" Note: {trimmed_notes}" if trimmed_notes else ""
    change_claim_status(
        session,
        claim,
        ClaimStatus.SETTLED,
        UserRole(actor.role),
        actor.id,
        (
            f"Simulated settlement {settlement.settlement_reference} completed for "
            f"{settlement.currency} {settlement.amount}.{note_suffix}"
        ),
    )

    return _settlement_envelope(claim, settlement)
