import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim
from app.models.user import User


def get_claim_for_user(session: Session, claim_id: uuid.UUID, user: User) -> Claim | None:
    # Staff (OPS, ADMIN) can see any claim.
    # Policyholders are limited to claims for their own business.
    # Returning None for both "missing" and "not yours" means the route
    # responds 404 either way, so existence is not revealed.
    query = select(Claim).where(Claim.id == claim_id)

    if user.role == "POLICYHOLDER":
        query = query.where(Claim.business_id == user.business_id)

    return session.execute(query).scalar_one_or_none()