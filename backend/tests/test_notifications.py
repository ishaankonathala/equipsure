import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Notification, User
from app.models.enums import ClaimStatus, UserRole
from app.workflow.service import change_claim_status
from app.workflow.transitions import TransitionError


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


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


def _token_for(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


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


def test_user_lists_only_their_own_notifications(
    client, session, business, claim
):
    owner = _make_policyholder(session, business)
    other_owner = _make_policyholder(session, business)
    own_notification = Notification(
        user_id=owner.id,
        claim_id=claim.id,
        kind="CLAIM_STATUS_CHANGED",
        message="Your claim was updated.",
    )
    other_notification = Notification(
        user_id=other_owner.id,
        claim_id=claim.id,
        kind="CLAIM_STATUS_CHANGED",
        message="Another user's claim was updated.",
    )
    session.add_all([own_notification, other_notification])
    session.flush()

    response = client.get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [str(own_notification.id)]


def test_mark_read_sets_timestamp_and_preserves_it_on_repeat(
    client, session, business, claim
):
    owner = _make_policyholder(session, business)
    notification = Notification(
        user_id=owner.id,
        claim_id=claim.id,
        kind="CLAIM_STATUS_CHANGED",
        message="Your claim was updated.",
    )
    session.add(notification)
    session.flush()
    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    path = f"/api/notifications/{notification.id}/read"

    first_response = client.patch(path, headers=headers)
    second_response = client.patch(path, headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_read_at = first_response.json()["read_at"]
    assert first_read_at is not None
    assert second_response.json()["read_at"] == first_read_at


def test_user_cannot_mark_another_users_notification_read(
    client, session, business, claim
):
    owner = _make_policyholder(session, business)
    other_owner = _make_policyholder(session, business)
    notification = Notification(
        user_id=other_owner.id,
        claim_id=claim.id,
        kind="CLAIM_STATUS_CHANGED",
        message="Another user's claim was updated.",
    )
    session.add(notification)
    session.flush()

    response = client.patch(
        f"/api/notifications/{notification.id}/read",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == 404