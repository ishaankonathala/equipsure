import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import ClaimMessage, User
from app.models.enums import MessageAuthorRole
from app.services.messaging import list_messages, post_message


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