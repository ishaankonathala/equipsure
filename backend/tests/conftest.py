import uuid
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.test_database import get_test_database_url
from app.models import Business, Claim, Equipment, Policy, User


ALEMBIC_INI = "alembic.ini"


@pytest.fixture(scope="session")
def engine():
    url = get_test_database_url()
    engine = create_engine(url, pool_pre_ping=True)

    config = Config(ALEMBIC_INI)
    config.attributes["database_url"] = url
    command.upgrade(config, "head")

    yield engine

    command.downgrade(config, "base")
    engine.dispose()


@pytest.fixture
def session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def business(session):
    obj = Business(id=uuid.uuid4(), name="Test Cafe")
    session.add(obj)
    session.flush()
    return obj


@pytest.fixture
def policyholder_user(session, business):
    obj = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="not-a-real-hash",
        full_name="Test Owner",
        role="POLICYHOLDER",
        business_id=business.id,
        is_active=True,
    )
    session.add(obj)
    session.flush()
    return obj


@pytest.fixture
def equipment(session, business):
    obj = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="REFRIGERATION",
        description="Test fridge",
    )
    session.add(obj)
    session.flush()
    return obj


@pytest.fixture
def policy(session, business):
    obj = Policy(
        id=uuid.uuid4(),
        policy_number="TEST-POL-1",
        business_id=business.id,
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        premium_amount=Decimal("100.00"),
        deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    session.add(obj)
    session.flush()
    return obj


@pytest.fixture
def claim(session, business, policy, equipment):
    obj = Claim(
        id=uuid.uuid4(),
        reference="TEST-000001",
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status="SUBMITTED",
        incident_date=date(2026, 10, 1),
        incident_description="Test incident",
        amount_claimed=Decimal("1200.00"),
    )
    session.add(obj)
    session.flush()
    return obj