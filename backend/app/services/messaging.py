from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimMessage, User


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