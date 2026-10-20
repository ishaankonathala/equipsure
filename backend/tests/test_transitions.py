import pytest

from app.models.enums import ClaimStatus, UserRole
from app.workflow.transitions import (
    ALLOWED_TRANSITIONS,
    OPEN_STATUSES,
    TransitionError,
    can_transition,
    check_transition,
)


def test_every_status_has_a_transition_entry():
    assert set(ALLOWED_TRANSITIONS) == set(ClaimStatus)


def test_happy_path_is_allowed():
    transitions = (
        (ClaimStatus.SUBMITTED, ClaimStatus.UNDER_VERIFICATION),
        (ClaimStatus.UNDER_VERIFICATION, ClaimStatus.UNDER_REVIEW),
        (ClaimStatus.UNDER_REVIEW, ClaimStatus.DECISION_PENDING),
        (ClaimStatus.DECISION_PENDING, ClaimStatus.APPROVED),
        (ClaimStatus.APPROVED, ClaimStatus.SETTLEMENT_IN_PROGRESS),
        (ClaimStatus.SETTLEMENT_IN_PROGRESS, ClaimStatus.SETTLED),
        (ClaimStatus.SETTLED, ClaimStatus.CLOSED),
    )

    for current, target in transitions:
        check_transition(current, target, UserRole.OPS)


def test_skipping_a_step_is_rejected():
    assert can_transition(ClaimStatus.SUBMITTED, ClaimStatus.APPROVED) is False
    with pytest.raises(TransitionError):
        check_transition(ClaimStatus.SUBMITTED, ClaimStatus.APPROVED, UserRole.OPS)


def test_closed_and_withdrawn_are_terminal():
    for target in ClaimStatus:
        assert can_transition(ClaimStatus.CLOSED, target) is False
        assert can_transition(ClaimStatus.WITHDRAWN, target) is False


def test_withdraw_allowed_from_every_open_status():
    for current in OPEN_STATUSES:
        assert can_transition(current, ClaimStatus.WITHDRAWN) is True


def test_withdrawn_not_allowed_from_closed_states():
    for current in (
        ClaimStatus.APPROVED,
        ClaimStatus.REJECTED,
        ClaimStatus.SETTLEMENT_IN_PROGRESS,
        ClaimStatus.SETTLED,
        ClaimStatus.CLOSED,
    ):
        assert can_transition(current, ClaimStatus.WITHDRAWN) is False


def test_policyholder_can_withdraw():
    check_transition(
        ClaimStatus.SUBMITTED,
        ClaimStatus.WITHDRAWN,
        UserRole.POLICYHOLDER,
    )


def test_policyholder_cannot_advance_claim():
    with pytest.raises(TransitionError, match="Policyholders"):
        check_transition(
            ClaimStatus.SUBMITTED,
            ClaimStatus.UNDER_VERIFICATION,
            UserRole.POLICYHOLDER,
        )


def test_ops_and_admin_can_advance():
    check_transition(
        ClaimStatus.SUBMITTED,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.OPS,
    )
    check_transition(
        ClaimStatus.SUBMITTED,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.ADMIN,
    )


def test_open_statuses_are_derived():
    assert OPEN_STATUSES == {
        status
        for status, targets in ALLOWED_TRANSITIONS.items()
        if ClaimStatus.WITHDRAWN in targets
    }
