from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Policy, User
from app.services.policy_document import build_policy_document_html

router = APIRouter(tags=["policies"])


class PolicyItem(BaseModel):
    id: str
    policy_number: str
    status: str
    start_date: str
    end_date: str
    premium_amount: Decimal
    coverage_limit: Decimal
    deductible_amount: Decimal


@router.get("", response_model=list[PolicyItem])
@router.get("/", response_model=list[PolicyItem], include_in_schema=False)
def list_policies(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Policy)
    if user.role == "POLICYHOLDER":
        query = query.where(Policy.business_id == user.business_id)
    elif user.role in {"OPS", "ADMIN"}:
        if user.business_id:
            query = query.where(Policy.business_id == user.business_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted",
        )

    query = query.order_by(Policy.created_at.desc(), Policy.id.desc())
    policies = db.execute(query).scalars().all()

    return [
        {
            "id": str(p.id),
            "policy_number": p.policy_number,
            "status": p.status,
            "start_date": str(p.start_date),
            "end_date": str(p.end_date),
            "premium_amount": p.premium_amount,
            "coverage_limit": p.coverage_limit,
            "deductible_amount": p.deductible_amount,
        }
        for p in policies
    ]


@router.get("/{policy_id}/document")
def download_policy_document(
    policy_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        parsed_id = uuid.UUID(str(policy_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Policy not found",
        )

    policy = db.get(Policy, parsed_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Policy not found",
        )

    if user.role == "POLICYHOLDER":
        if policy.business_id != user.business_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found",
            )
    elif user.role in {"OPS", "ADMIN"}:
        # OPS and ADMIN may download any policy
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted",
        )

    html_content = build_policy_document_html(db, policy)
    filename = f"{policy.policy_number}.html"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return Response(
        content=html_content,
        media_type="text/html",
        headers=headers,
    )

