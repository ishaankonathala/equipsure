import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Claim
from app.models.user import User
from app.services.claims import get_claim_for_user

router = APIRouter()


@router.get("/{claim_id}")
def read_claim(
    claim_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    return {
        "id": str(claim.id),
        "reference": claim.reference,
        "business_id": str(claim.business_id),
        "policy_id": str(claim.policy_id),
        "equipment_id": str(claim.equipment_id),
        "status": claim.status,
        "incident_date": claim.incident_date.isoformat(),
        "amount_claimed": str(claim.amount_claimed),
    }