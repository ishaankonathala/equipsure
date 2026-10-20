import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import (
    BillingRecord,
    Business,
    Claim,
    ClaimEvent,
    Equipment,
    Policy,
    PolicyEquipment,
    User,
)
from scripts.seed import (
    check_not_test_database,
    read_seed_passwords,
    seed_billing,
    seed_business,
    seed_claim,
    seed_equipment,
    seed_policy,
    seed_policy_equipment,
    seed_users,
)

TEST_PASSWORDS = {
    "SEED_POLICYHOLDER_PASSWORD": "test-policyholder-pass",
    "SEED_OPS_PASSWORD": "test-ops-pass",
    "SEED_ADMIN_PASSWORD": "test-admin-pass",
}


@pytest.fixture
def seed_env(monkeypatch):
    for name, value in TEST_PASSWORDS.items():
        monkeypatch.setenv(name, value)


def _run_seed(session):
    business = seed_business(session)
    users = seed_users(session, TEST_PASSWORDS, business)
    equipment_list = seed_equipment(session, business)
    policy = seed_policy(session, business)
    seed_policy_equipment(session, policy, equipment_list)
    seed_billing(session, policy)
    seed_claim(session, business, policy, equipment_list, users)
    session.flush()


def _counts(session):
    def count(model):
        return session.execute(select(func.count()).select_from(model)).scalar_one()

    return {
        "business": count(Business),
        "users": count(User),
        "equipment": count(Equipment),
        "policy": count(Policy),
        "policy_equipment": count(PolicyEquipment),
        "billing": count(BillingRecord),
        "claim": count(Claim),
        "claim_events": count(ClaimEvent),
    }


def test_guard_refuses_test_database(monkeypatch):
    monkeypatch.setattr(settings, "postgres_db", settings.test_postgres_db)
    url = f"postgresql+psycopg://u:p@localhost:5432/{settings.test_postgres_db}"
    with pytest.raises(SystemExit):
        check_not_test_database(url)


def test_guard_allows_dev_database():
    url = f"postgresql+psycopg://u:p@localhost:5432/{settings.postgres_db}"
    check_not_test_database(url)


def test_missing_passwords_refuse(monkeypatch):
    for name in TEST_PASSWORDS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit):
        read_seed_passwords()


def test_seed_creates_one_of_each(session, seed_env):
    _run_seed(session)
    counts = _counts(session)
    assert counts["business"] == 1
    assert counts["users"] == 3
    assert counts["equipment"] == 2
    assert counts["policy"] == 1
    assert counts["policy_equipment"] == 2
    assert counts["billing"] == 1
    assert counts["claim"] == 1
    assert counts["claim_events"] == 1


def test_seed_is_idempotent(session, seed_env):
    _run_seed(session)
    first = _counts(session)
    _run_seed(session)
    second = _counts(session)
    assert second == first
    assert second["claim_events"] == 1
