import uuid
from decimal import Decimal

from app.models import ClaimDocument, PolicyEquipment
from app.services.review import evaluate_claim


def _link(session, policy, equipment):
    session.add(PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id))
    session.flush()


def _doc(session, claim, doc_type):
    session.add(ClaimDocument(
        id=uuid.uuid4(),
        claim_id=claim.id,
        document_type=doc_type,
        original_filename="f.pdf",
        storage_name=uuid.uuid4().hex,
        content_type="application/pdf",
        size_bytes=10,
        sha256="a" * 64,
    ))
    session.flush()


def test_suggested_amount_is_claimed_minus_deductible(session, business, policy, equipment, claim):
    _link(session, policy, equipment)
    _doc(session, claim, "INVOICE")
    _doc(session, claim, "PHOTO")
    summary = evaluate_claim(session, claim)
    assert summary.suggested_amount == Decimal("700.00")
    assert summary.all_passed is True


def test_uncovered_equipment_suggests_zero(session, business, policy, equipment, claim):
    summary = evaluate_claim(session, claim)
    assert summary.suggested_amount == Decimal("0.00")
    failed = [c.name for c in summary.checks if not c.passed]
    assert "Equipment covered by policy" in failed

