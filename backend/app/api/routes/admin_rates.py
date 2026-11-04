from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models import PremiumRate, User

router = APIRouter(tags=["admin_rates"])


class RateItem(BaseModel):
    kind: str
    code: str
    value: Decimal


class RateUpdateRequest(BaseModel):
    value: Decimal

    @field_validator("value")
    @classmethod
    def check_non_negative(cls, v: Decimal) -> Decimal:
        if v < Decimal("0"):
            raise ValueError("Rate value must be greater than or equal to 0")
        return v


@router.get("", response_model=list[RateItem])
@router.get("/", response_model=list[RateItem], include_in_schema=False)
def list_rates(
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rates = db.execute(
        select(PremiumRate).order_by(PremiumRate.kind, PremiumRate.code)
    ).scalars().all()
    return [{"kind": r.kind, "code": r.code, "value": r.value} for r in rates]


@router.put("/{kind}/{code}", response_model=RateItem)
def update_rate(
    kind: str,
    code: str,
    payload: RateUpdateRequest,
    user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> dict:
    normalized_kind = kind.strip().upper()
    rate = db.execute(
        select(PremiumRate).where(
            PremiumRate.kind == normalized_kind,
            PremiumRate.code == code.strip(),
        )
    ).scalar_one_or_none()

    if rate is None:
        rate = db.execute(
            select(PremiumRate).where(
                PremiumRate.kind == normalized_kind,
                PremiumRate.code == code.strip().upper(),
            )
        ).scalar_one_or_none()

    if rate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rate not found",
        )

    rate.value = payload.value
    db.commit()
    db.refresh(rate)
    return {"kind": rate.kind, "code": rate.code, "value": rate.value}

