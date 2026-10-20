import pytest
from sqlalchemy import func, select

from app.models import ClaimEvent
from app.models.enums import ClaimStatus, UserRole
from app.workflow.service import change_claim_status
from app.workflow.transitions import TransitionError


def _event_count(session, claim):
    return session.execute(
        select(func.count())
        .select_from(ClaimEvent)
        .where(ClaimEvent.claim_id == claim.id)
    ).scalar_one()


def test_legal_move_writes_one_event(session, claim):
    event = change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.OPS,
        None,
        "Documents checked",
    )

    assert isinstance(event, ClaimEvent)
    assert claim.status == "UNDER_VERIFICATION"
    assert event.old_status == "SUBMITTED"
    assert event.new_status == "UNDER_VERIFICATION"
    assert event.source == "OPS"
    assert _event_count(session, claim) == 1


def test_illegal_move_writes_nothing(session, claim):
    with pytest.raises(TransitionError):
        change_claim_status(
            session,
            claim,
            ClaimStatus.APPROVED,
            UserRole.OPS,
            None,
            "Skip ahead",
        )

    assert claim.status == "SUBMITTED"
    assert _event_count(session, claim) == 0


def test_policyholder_cannot_advance(session, claim):
    with pytest.raises(TransitionError, match="Policyholders"):
        change_claim_status(
            session,
            claim,
            ClaimStatus.UNDER_VERIFICATION,
            UserRole.POLICYHOLDER,
            None,
            "Trying to advance",
        )

    assert claim.status == "SUBMITTED"
    assert _event_count(session, claim) == 0


def test_policyholder_can_withdraw(session, claim):
    event = change_claim_status(
        session,
        claim,
        ClaimStatus.WITHDRAWN,
        UserRole.POLICYHOLDER,
        None,
        "Customer withdrew",
    )

    assert claim.status == "WITHDRAWN"
    assert event.source == "POLICYHOLDER"


def test_blank_explanation_rejected(session, claim):
    with pytest.raises(ValueError, match="Explanation is required"):
        change_claim_status(
            session,
            claim,
            ClaimStatus.UNDER_VERIFICATION,
            UserRole.OPS,
            None,
            "   ",
        )

    assert claim.status == "SUBMITTED"
    assert _event_count(session, claim) == 0


def test_sequential_moves_append_events(session, claim):
    first_event = change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.OPS,
        None,
        "Initial review",
    )
    second_event = change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_REVIEW,
        UserRole.OPS,
        None,
        "Documents verified",
    )

    assert _event_count(session, claim) == 2
    assert first_event.old_status == "SUBMITTED"
    assert first_event.new_status == "UNDER_VERIFICATION"
    assert second_event.old_status == "UNDER_VERIFICATION"
    assert second_event.new_status == "UNDER_REVIEW"