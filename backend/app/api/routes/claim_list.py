from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Claim
from app.models.user import User

router = APIRouter()


@router.get("")
def list_claims(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Claim).order_by(Claim.created_at.desc(), Claim.id.desc())
    if user.role == "POLICYHOLDER":
        query = query.where(Claim.business_id == user.business_id)
    elif user.role not in {"OPS", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")
    claims = db.execute(query).scalars().all()
    return [
        {
            "id": str(claim.id),
            "reference": claim.reference,
            "business_id": str(claim.business_id),
            "policy_id": str(claim.policy_id),
            "equipment_id": str(claim.equipment_id),
            "status": claim.status,
            "incident_date": claim.incident_date.isoformat(),
            "amount_claimed": str(claim.amount_claimed),
        }
        for claim in claims
    ]