from decimal import Decimal
import uuid
import pytest

from app.core.security import hash_password
from app.models import ClaimDocument, ClaimEvent, PolicyEquipment, User
from app.models.enums import ClaimStatus, UserRole
from app.services.review_decision import ReviewDecisionError, decide_claim


def _setup_reviewable_claim(session, policy, equipment, claim):
    claim.amount_claimed = Decimal("800.00")
    claim.status = ClaimStatus.DECISION_PENDING.value
    session.add(PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id))
    for doc_type in ("INVOICE", "PHOTO"):
        session.add(
            ClaimDocument(
                id=uuid.uuid4(),
                claim_id=claim.id,
                document_type=doc_type,
                original_filename="f.pdf",
                storage_name=uuid.uuid4().hex,
                content_type="application/pdf",
                size_bytes=10,
                sha256="a" * 64,
            )
        )
    session.flush()


def _make_ops_user(session):
    user = User(
        id=uuid.uuid4(),
        email=f"ops-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("test-pass"),
        full_name="Test OPS Officer",
        role=UserRole.OPS.value,
        business_id=None,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def test_approve_at_suggested_amount_without_reason_moves_claim_and_writes_event(
    session, business, policy, equipment, claim
):
    _setup_reviewable_claim(session, policy, equipment, claim)
    ops = _make_ops_user(session)

    new_status, explanation = decide_claim(
        session,
        claim,
        ops,
        decision="APPROVE",
        approved_amount=Decimal("300.00"),
        reason=None,
    )

    assert new_status == ClaimStatus.APPROVED.value
    assert claim.status == ClaimStatus.APPROVED.value
    assert "Approved by officer" in explanation
    assert "Suggested 300.00, approved 300.00" in explanation

    events = session.query(ClaimEvent).filter(ClaimEvent.claim_id == claim.id).all()
    assert len(events) == 1
    assert events[0].new_status == ClaimStatus.APPROVED.value
    assert events[0].explanation == explanation


def test_approve_at_different_amount_without_reason_raises(
    session, business, policy, equipment, claim
):
    _setup_reviewable_claim(session, policy, equipment, claim)
    ops = _make_ops_user(session)

    with pytest.raises(
        ReviewDecisionError, match="reason is required when the amount differs"
    ):
        decide_claim(
            session,
            claim,
            ops,
            decision="APPROVE",
            approved_amount=Decimal("250.00"),
            reason=None,
        )


def test_approve_at_different_amount_with_reason_succeeds_and_contains_both_amounts(
    session, business, policy, equipment, claim
):
    _setup_reviewable_claim(session, policy, equipment, claim)
    ops = _make_ops_user(session)

    new_status, explanation = decide_claim(
        session,
        claim,
        ops,
        decision="APPROVE",
        approved_amount=Decimal("250.00"),
        reason="Adjusted for salvage value.",
    )

    assert new_status == ClaimStatus.APPROVED.value
    assert claim.status == ClaimStatus.APPROVED.value
    assert "300.00" in explanation
    assert "250.00" in explanation
    assert "Adjusted for salvage value." in explanation

    events = session.query(ClaimEvent).filter(ClaimEvent.claim_id == claim.id).all()
    assert len(events) == 1
    assert events[0].explanation == explanation


def test_reject_without_reason_raises(session, business, policy, equipment, claim):
    _setup_reviewable_claim(session, policy, equipment, claim)
    ops = _make_ops_user(session)

    with pytest.raises(ReviewDecisionError, match="reason is required to reject"):
        decide_claim(
            session,
            claim,
            ops,
            decision="REJECT",
            approved_amount=None,
            reason=None,
        )


def test_approve_above_claimed_amount_raises(
    session, business, policy, equipment, claim
):
    _setup_reviewable_claim(session, policy, equipment, claim)
    ops = _make_ops_user(session)

    with pytest.raises(
        ReviewDecisionError, match="between 0 and the claimed amount"
    ):
        decide_claim(
            session,
            claim,
            ops,
            decision="APPROVE",
            approved_amount=Decimal("900.00"),
            reason="Exceeds claim",
        )

