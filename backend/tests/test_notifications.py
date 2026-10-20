import uuid

import pytest
from sqlalchemy import func, select

from app.models import Notification, User
from app.models.enums import ClaimStatus, UserRole
from app.workflow.service import change_claim_status
from app.workflow.transitions import TransitionError


def _make_policyholder(session, business, is_active=True):
    user = User(
        id=uuid.uuid4(),
        email=f"notify-{uuid.uuid4().hex}@example.com",
        password_hash="not-a-real-hash",
        full_name="Notification Policyholder",
        role=UserRole.POLICYHOLDER.value,
        business_id=business.id,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def _notification_count(session, claim):
    return session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.claim_id == claim.id)
    ).scalar_one()


def test_legal_status_change_notifies_matching_policyholder(
    session, business, claim
):
    policyholder = _make_policyholder(session, business)

    change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.OPS,
        None,
        "Documents checked",
    )

    notifications = session.execute(
        select(Notification).where(
            Notification.user_id == policyholder.id,
            Notification.claim_id == claim.id,
            Notification.kind == "CLAIM_STATUS_CHANGED",
        )
    ).scalars().all()

    assert len(notifications) == 1
    assert _notification_count(session, claim) == 1
    assert claim.reference in notifications[0].message


def test_status_change_without_active_policyholder_creates_no_notification(
    session, business, claim
):
    _make_policyholder(session, business, is_active=False)

    change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_VERIFICATION,
        UserRole.OPS,
        None,
        "Documents checked",
    )

    assert _notification_count(session, claim) == 0


def test_illegal_status_change_creates_no_notification(
    session, business, claim
):
    _make_policyholder(session, business)

    with pytest.raises(TransitionError):
        change_claim_status(
            session,
            claim,
            ClaimStatus.APPROVED,
            UserRole.OPS,
            None,
            "Skip ahead",
        )

    assert _notification_count(session, claim) == 0