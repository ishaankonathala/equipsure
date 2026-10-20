from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimMessage, Notification, User


def post_message(
    session: Session, claim: Claim, author: User, body: str
) -> ClaimMessage:
    trimmed_body = body.strip()
    if not trimmed_body:
        raise ValueError("Message body is required")
    if len(trimmed_body) > 2000:
        raise ValueError("Message is too long")

    message = ClaimMessage(
        claim_id=claim.id,
        author_user_id=author.id,
        author_role=author.role,
        body=trimmed_body,
    )
    session.add(message)
    session.flush()
    return message


def list_messages(session: Session, claim: Claim) -> list[ClaimMessage]:
    return session.execute(
        select(ClaimMessage)
        .where(ClaimMessage.claim_id == claim.id)
        .order_by(ClaimMessage.created_at.asc(), ClaimMessage.id.asc())
    ).scalars().all()


def create_notification(
    session: Session,
    user_id,
    claim_id,
    kind: str,
    message: str,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        claim_id=claim_id,
        kind=kind,
        message=message,
    )
    session.add(notification)
    session.flush()
    return notification


def list_notifications(session: Session, user: User) -> list[Notification]:
    return session.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(
            Notification.read_at.is_not(None).asc(),
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
    ).scalars().all()


def mark_read(
    session: Session, notification: Notification, user: User
) -> Notification:
    if notification.user_id != user.id:
        raise PermissionError
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
    session.flush()
    return notification