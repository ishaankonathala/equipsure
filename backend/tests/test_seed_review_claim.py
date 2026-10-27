import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Claim, ClaimEvent, Equipment
from app.models.enums import EquipmentCategory
from scripts.seed import seed_review_claim


def _setup(session, business, policy):
    oven = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category=EquipmentCategory.COOKING.value,
        description="Test oven",
    )
    session.add(oven)
    session.flush()
    return [oven]


def _users(session, business):
    from app.core.security import hash_password
    from app.models import User

    owner = User(
        id=uuid.uuid4(),
        email="owner-seed@example.com",
        password_hash=hash_password("x-owner"),
        full_name="Owner",
        role="POLICYHOLDER",
        business_id=business.id,
        is_active=True,
    )
    ops = User(
        id=uuid.uuid4(),
        email="ops-seed@example.com",
        password_hash=hash_password("x-ops"),
        full_name="Ops",
        role="OPS",
        business_id=None,
        is_active=True,
    )
    session.add_all([owner, ops])
    session.flush()
    return {
        "cafe.owner@equipsure.demo": owner,
        "ops.officer@equipsure.demo": ops,
    }


def _event_count(session, claim_id):
    return session.execute(
        select(func.count()).select_from(ClaimEvent).where(ClaimEvent.claim_id == claim_id)
    ).scalar_one()


def test_review_claim_reaches_under_review_with_three_events(session, business, policy):
    equipment_list = _setup(session, business, policy)
    users = _users(session, business)

    claim = seed_review_claim(session, business, policy, equipment_list, users)

    assert claim.reference == "DEMO-000002"
    assert claim.status == "UNDER_REVIEW"
    assert _event_count(session, claim.id) == 3


def test_review_claim_is_idempotent(session, business, policy):
    equipment_list = _setup(session, business, policy)
    users = _users(session, business)

    first = seed_review_claim(session, business, policy, equipment_list, users)
    before = _event_count(session, first.id)
    second = seed_review_claim(session, business, policy, equipment_list, users)

    assert second.id == first.id
    assert _event_count(session, first.id) == before == 3