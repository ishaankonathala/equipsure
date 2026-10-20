import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Business, Equipment, Policy, User


def test_test_database_is_migrated(session):
    version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0002"


def test_user_rejects_invalid_role(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="bad-role@example.com", password_hash="x",
                full_name="Bad Role", role="ADMINX", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_user_rejects_duplicate_email(session, business):
    session.add(User(
        id=uuid.uuid4(), email="dup@example.com", password_hash="x",
        full_name="First", role="POLICYHOLDER", business_id=business.id, is_active=True,
    ))
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="dup@example.com", password_hash="x",
                full_name="Second", role="POLICYHOLDER", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_user_rejects_uppercase_email(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="Upper@Example.com", password_hash="x",
                full_name="Upper", role="POLICYHOLDER", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_policyholder_requires_business(session):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="nobiz@example.com", password_hash="x",
                full_name="No Biz", role="POLICYHOLDER", business_id=None, is_active=True,
            ))
            session.flush()


def test_ops_user_may_have_no_business(session):
    session.add(User(
        id=uuid.uuid4(), email="ops@example.com", password_hash="x",
        full_name="Ops", role="OPS", business_id=None, is_active=True,
    ))
    session.flush()


def test_policy_rejects_end_before_start(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Policy(
                id=uuid.uuid4(), policy_number="BAD-DATES", business_id=business.id,
                status="ACTIVE", start_date=date(2027, 1, 1), end_date=date(2026, 1, 1),
                premium_amount=Decimal("100.00"), deductible_amount=Decimal("500.00"),
                coverage_limit=Decimal("50000.00"),
            ))
            session.flush()