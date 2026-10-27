from datetime import date
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Claim
from app.models.user import User
from app.services.claims import (
    ClaimRegistrationError,
    MAX_CLAIM_AMOUNT,
    MAX_DESCRIPTION_LENGTH,
    register_claim_for_user,
)

router = APIRouter()


class ClaimCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    policy_number: str = Field(min_length=1, max_length=40)
    equipment_id: uuid.UUID
    incident_date: date
    incident_description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    amount_claimed: Decimal = Field(gt=Decimal("0"), le=MAX_CLAIM_AMOUNT, decimal_places=2)


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
    officer_ids = {
        claim.assigned_officer_id
        for claim in claims
        if claim.assigned_officer_id is not None
    }
    officers_by_id: dict[uuid.UUID, User] = {}
    if officer_ids:
        officers = (
            db.execute(select(User).where(User.id.in_(officer_ids)))
            .scalars()
            .all()
        )
        officers_by_id = {officer.id: officer for officer in officers}

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
            "assigned_officer_id": (
                str(claim.assigned_officer_id)
                if claim.assigned_officer_id is not None
                else None
            ),
            "assigned_officer_name": (
                officers_by_id[claim.assigned_officer_id].full_name
                if claim.assigned_officer_id in officers_by_id
                else None
            ),
            "assigned_at": (
                claim.assigned_at.isoformat()
                if claim.assigned_at is not None
                else None
            ),
        }
        for claim in claims
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_claim(
    payload: ClaimCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "POLICYHOLDER" or user.business_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only policyholders may register claims",
        )

    try:
        result = register_claim_for_user(
            db,
            user,
            policy_number=payload.policy_number,
            equipment_id=payload.equipment_id,
            incident_date=payload.incident_date,
            incident_description=payload.incident_description,
            amount_claimed=payload.amount_claimed,
        )
        db.commit()
    except ClaimRegistrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.detail,
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except Exception:
        db.rollback()
        raise

    claim = result.claim
    return {
        "id": str(claim.id),
        "reference": claim.reference,
        "business_id": str(claim.business_id),
        "policy_id": str(claim.policy_id),
        "equipment_id": str(claim.equipment_id),
        "status": claim.status,
        "incident_date": claim.incident_date.isoformat(),
        "incident_description": claim.incident_description,
        "amount_claimed": str(claim.amount_claimed),
        "sources": list(result.sources),
    }
