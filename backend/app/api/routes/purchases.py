from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import PremiumQuote, PremiumRate, User
from app.services.premium import calculate_premium
from app.services.purchase import PurchaseError, purchase_quote

router = APIRouter(tags=["quotes"])


class CreateQuoteRequest(BaseModel):
    equipment_category: str
    equipment_description: str
    sum_insured: Decimal = Field(gt=Decimal("0"))
    age_years: int = Field(ge=0)
    cover: str


def _format_quote(quote: PremiumQuote) -> dict:
    return {
        "id": str(quote.id),
        "business_id": str(quote.business_id),
        "created_by_user_id": str(quote.created_by_user_id),
        "equipment_category": quote.equipment_category,
        "equipment_description": quote.equipment_description,
        "sum_insured": quote.sum_insured,
        "age_years": quote.age_years,
        "cover": quote.cover,
        "total": quote.total,
        "lines": quote.lines,
        "status": quote.status,
        "policy_id": str(quote.policy_id) if quote.policy_id else None,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_quote(
    body: CreateQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.business_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business ID is required to create a quote",
        )

    rates = db.execute(select(PremiumRate)).scalars().all()
    rates_mapping = {(r.kind, r.code): r.value for r in rates}

    try:
        calc = calculate_premium(
            category=body.equipment_category,
            sum_insured=body.sum_insured,
            age_years=body.age_years,
            cover=body.cover,
            rates=rates_mapping,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    lines = [
        {"label": line.label, "amount": str(line.amount)}
        for line in calc.lines
    ]

    quote = PremiumQuote(
        id=uuid.uuid4(),
        business_id=user.business_id,
        created_by_user_id=user.id,
        equipment_category=calc.category,
        equipment_description=body.equipment_description.strip(),
        sum_insured=body.sum_insured,
        age_years=body.age_years,
        cover=calc.cover,
        total=calc.total,
        lines=lines,
        status="OPEN",
        policy_id=None,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)

    return _format_quote(quote)


@router.get("/compare")
def compare_quotes(
    ids: list[str] = Query(default_factory=list),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    if len(ids) not in (2, 3):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Must provide 2 or 3 quote IDs to compare",
        )

    parsed_ids: list[uuid.UUID] = []
    for raw_id in ids:
        try:
            parsed_ids.append(uuid.UUID(str(raw_id).strip()))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quote not found",
            )

    quotes_by_id: dict[uuid.UUID, PremiumQuote] = {}
    for p_id in parsed_ids:
        quote = db.get(PremiumQuote, p_id)
        if quote is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quote not found",
            )
        if quote.business_id != user.business_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quote not found",
            )
        quotes_by_id[p_id] = quote

    return [_format_quote(quotes_by_id[p_id]) for p_id in parsed_ids]


@router.get("")
@router.get("/", include_in_schema=False)
def list_quotes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(PremiumQuote)
    if user.role == "POLICYHOLDER":
        query = query.where(PremiumQuote.business_id == user.business_id)
    elif user.role in {"OPS", "ADMIN"}:
        if user.business_id:
            query = query.where(PremiumQuote.business_id == user.business_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted",
        )

    query = query.order_by(PremiumQuote.created_at.desc(), PremiumQuote.id.desc())
    quotes = db.execute(query).scalars().all()
    return [_format_quote(q) for q in quotes]


@router.post("/{quote_id}/purchase")
def purchase_quote_route(
    quote_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "POLICYHOLDER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only policyholders can purchase quotes",
        )

    try:
        parsed_id = uuid.UUID(str(quote_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    quote = db.get(PremiumQuote, parsed_id)
    if quote is None or quote.business_id != user.business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    if quote.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quote has already been purchased",
        )

    try:
        result = purchase_quote(db, quote, user)
        db.commit()
    except PurchaseError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception:
        db.rollback()
        raise

    return result

