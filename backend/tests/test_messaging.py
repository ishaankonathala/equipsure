import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status as http_status
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Business, ClaimMessage, User
from app.models.enums import MessageAuthorRole
from app.services.messaging import list_messages, post_message


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_author(session, business, role=MessageAuthorRole.POLICYHOLDER):
    author = User(
        id=uuid.uuid4(),
        email=f"message-{uuid.uuid4().hex}@example.com",
        password_hash="not-a-real-hash",
        full_name="Message Author",
        role=role.value,
        business_id=business.id,
        is_active=True,
    )
    session.add(author)
    session.flush()
    return author


def _token_for(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def test_post_message_stores_trimmed_body_and_author_role(
    session, business, claim
):
    author = _make_author(session, business, MessageAuthorRole.OPS)

    message = post_message(session, claim, author, "  Checked the claim.  ")

    assert isinstance(message, ClaimMessage)
    assert message.body == "Checked the claim."
    assert message.author_user_id == author.id
    assert message.author_role == MessageAuthorRole.OPS.value


def test_post_message_rejects_empty_or_whitespace_body(session, business, claim):
    author = _make_author(session, business)

    for body in ("", " \t\n "):
        with pytest.raises(ValueError) as exc_info:
            post_message(session, claim, author, body)
        assert str(exc_info.value) == "Message body is required"


def test_post_message_rejects_body_longer_than_2000_characters(
    session, business, claim
):
    author = _make_author(session, business)

    with pytest.raises(ValueError) as exc_info:
        post_message(session, claim, author, "x" * 2001)

    assert str(exc_info.value) == "Message is too long"


def test_list_messages_returns_creation_order(session, business, claim):
    author = _make_author(session, business)
    first = post_message(session, claim, author, "First message")
    second = post_message(session, claim, author, "Second message")
    first.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second.created_at = first.created_at + timedelta(seconds=1)
    session.flush()

    messages = list_messages(session, claim)

    assert messages == [first, second]


def test_claim_owner_can_post_message(client, session, business, claim):
    owner = _make_author(session, business)
    response = client.post(
        f"/api/claims/{claim.id}/messages",
        json={"body": "  Please review this claim.  ", "author_role": "ADMIN"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    assert response.json()["body"] == "Please review this claim."
    assert response.json()["author_user_id"] == str(owner.id)
    assert response.json()["author_role"] == "POLICYHOLDER"


def test_other_business_user_gets_404_for_claim_messages(
    client, session, claim
):
    other_business = Business(id=uuid.uuid4(), name="Other Message Business")
    session.add(other_business)
    session.flush()
    other_user = _make_author(session, other_business)

    response = client.get(
        f"/api/claims/{claim.id}/messages",
        headers={"Authorization": f"Bearer {_token_for(other_user)}"},
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND