import uuid

from sqlalchemy import func, select

from app.integrations.mock_claimcenter import MockClaimCenter
from app.models import Claim, ClaimEvent


def _add_event(session, claim, old_status, new_status, explanation):
    event = ClaimEvent(
        claim_id=claim.id,
        old_status=old_status,
        new_status=new_status,
        source="OPS",
        actor_user_id=None,
        explanation=explanation,
    )
    session.add(event)
    session.flush()
    return event


def test_register_claim_rejects_existing_reference(session, claim):
    result = MockClaimCenter(session).register_claim("TEST-000001")

    assert result.ok is False
    assert result.reason == "Claim reference already exists"


def test_register_claim_accepts_new_reference(session):
    result = MockClaimCenter(session).register_claim("NEW-000999")

    assert result.ok is True
    assert result.data["reference"] == "NEW-000999"


def test_register_claim_does_not_create_a_row(session):
    MockClaimCenter(session).register_claim("NEW-000999")

    count = session.execute(
        select(func.count())
        .select_from(Claim)
        .where(Claim.reference == "NEW-000999")
    ).scalar_one()
    assert count == 0


def test_register_claim_rejects_blank_reference(session):
    result = MockClaimCenter(session).register_claim("   ")

    assert result.ok is False
    assert result.reason == "Claim reference is required"


def test_status_history_is_empty_for_new_claim(session, claim):
    result = MockClaimCenter(session).get_status_history(claim.id)

    assert result.ok is True
    assert result.data["events"] == []


def test_status_history_returns_events_in_order(session, claim):
    _add_event(
        session,
        claim,
        "SUBMITTED",
        "UNDER_VERIFICATION",
        "Verification started",
    )
    _add_event(
        session,
        claim,
        "UNDER_VERIFICATION",
        "UNDER_REVIEW",
        "Verification complete",
    )

    result = MockClaimCenter(session).get_status_history(claim.id)
    events = result.data["events"]

    assert result.ok is True
    assert len(events) == 2
    assert events[0]["old_status"] == "SUBMITTED"
    assert events[0]["new_status"] == "UNDER_VERIFICATION"
    assert events[1]["old_status"] == "UNDER_VERIFICATION"
    assert events[1]["new_status"] == "UNDER_REVIEW"


def test_status_history_unknown_claim(session):
    result = MockClaimCenter(session).get_status_history(uuid.uuid4())

    assert result.ok is False
    assert result.reason == "Claim not found"


def test_status_history_does_not_modify_claim(session, claim):
    original_status = claim.status

    MockClaimCenter(session).get_status_history(claim.id)

    assert claim.status == original_status