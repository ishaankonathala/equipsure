from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.services.claims import get_claim_for_user
from app.services.image_check import analyze_claim_image_flags

router = APIRouter(tags=["claim_images"])


@router.get("/{claim_id}/image-flags")
def get_claim_image_flags(
    claim_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = get_claim_for_user(db, claim_id, user)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found",
        )
    if user.role not in {"OPS", "ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted",
        )

    result = analyze_claim_image_flags(db, claim)
    db.commit()
    return result

