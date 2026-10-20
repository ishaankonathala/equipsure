import os
import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
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
from app.models.enums import (
    BillingStatus,
    ClaimStatus,
    EquipmentCategory,
    EventSource,
    PolicyStatus,
    UserRole,
)

REQUIRED_PASSWORD_VARS = (
    "SEED_POLICYHOLDER_PASSWORD",
    "SEED_OPS_PASSWORD",
    "SEED_ADMIN_PASSWORD",
)


def check_not_test_database(url: str) -> None:
    # Seeding must only ever target the development database.
    if settings.postgres_db == settings.test_postgres_db or url.endswith(
        f"/{settings.test_postgres_db}"
    ):
        raise SystemExit(
            f"Refusing to seed '{settings.test_postgres_db}'. Seed the development database only."
        )


def read_seed_passwords() -> dict[str, str]:
    missing = [name for name in REQUIRED_PASSWORD_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in REQUIRED_PASSWORD_VARS}


def seed_business(session: Session) -> Business:
    business = session.execute(
        select(Business).where(Business.name == "Hush Demo Cafe")
    ).scalar_one_or_none()
    if business is None:
        business = Business(id=uuid.uuid4(), name="Hush Demo Cafe")
        session.add(business)
        print("business: created")
        return business
    print("business: exists")
    return business


def seed_users(session: Session, passwords: dict[str, str], business: Business) -> dict[str, User]:
    user_specs = (
        (
            "cafe.owner@equipsure.demo",
            UserRole.POLICYHOLDER.value,
            business.id,
            "SEED_POLICYHOLDER_PASSWORD",
            "Demo Cafe Owner",
        ),
        (
            "ops.officer@equipsure.demo",
            UserRole.OPS.value,
            None,
            "SEED_OPS_PASSWORD",
            "Demo Ops Officer",
        ),
        (
            "admin@equipsure.demo",
            UserRole.ADMIN.value,
            None,
            "SEED_ADMIN_PASSWORD",
            "Demo Administrator",
        ),
    )

    created = False
    users: dict[str, User] = {}
    for email, role, business_id, var_name, full_name in user_specs:
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email=email,
                password_hash=hash_password(passwords[var_name]),
                full_name=full_name,
                role=role,
                business_id=business_id,
                is_active=True,
            )
            session.add(user)
            created = True
        users[email] = user

    print("users: created" if created else "users: exists")
    return users


def seed_equipment(session: Session, business: Business) -> list[Equipment]:
    equipment_specs = (
        ("Commercial refrigerator", EquipmentCategory.REFRIGERATION.value),
        ("Commercial convection oven", EquipmentCategory.COOKING.value),
    )
    created = False
    equipment_list: list[Equipment] = []
    for description, category in equipment_specs:
        item = session.execute(
            select(Equipment).where(
                Equipment.business_id == business.id,
                Equipment.description == description,
            )
        ).scalar_one_or_none()
        if item is None:
            item = Equipment(
                id=uuid.uuid4(),
                business_id=business.id,
                category=category,
                description=description,
            )
            session.add(item)
            created = True
        equipment_list.append(item)

    print("equipment: created" if created else "equipment: exists")
    return equipment_list


def seed_policy(session: Session, business: Business) -> Policy:
    policy = session.execute(
        select(Policy).where(Policy.policy_number == "DEMO-POL-0001")
    ).scalar_one_or_none()
    if policy is None:
        policy = Policy(
            id=uuid.uuid4(),
            policy_number="DEMO-POL-0001",
            business_id=business.id,
            status=PolicyStatus.ACTIVE.value,
            start_date=date(2026, 1, 1),
            end_date=date(2027, 1, 1),
            premium_amount=Decimal("1200.00"),
            deductible_amount=Decimal("500.00"),
            coverage_limit=Decimal("50000.00"),
        )
        session.add(policy)
        print("policy: created")
        return policy
    print("policy: exists")
    return policy


def seed_policy_equipment(session: Session, policy: Policy, equipment_list: list[Equipment]) -> None:
    created = False
    for equipment in equipment_list:
        existing = session.execute(
            select(PolicyEquipment).where(
                PolicyEquipment.policy_id == policy.id,
                PolicyEquipment.equipment_id == equipment.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id))
            created = True

    print("policy_equipment: created" if created else "policy_equipment: exists")


def seed_billing(session: Session, policy: Policy) -> BillingRecord:
    billing = session.execute(
        select(BillingRecord).where(
            BillingRecord.policy_id == policy.id,
            BillingRecord.period_start == date(2026, 1, 1),
        )
    ).scalar_one_or_none()
    if billing is None:
        billing = BillingRecord(
            id=uuid.uuid4(),
            policy_id=policy.id,
            period_start=date(2026, 1, 1),
            period_end=date(2027, 1, 1),
            amount_due=Decimal("1200.00"),
            amount_paid=Decimal("1200.00"),
            status=BillingStatus.PAID.value,
            due_date=date(2026, 2, 1),
        )
        session.add(billing)
        print("billing: created")
        return billing
    print("billing: exists")
    return billing


def seed_claim(
    session: Session,
    business: Business,
    policy: Policy,
    equipment_list: list[Equipment],
    users: dict[str, User],
) -> Claim:
    refrigerator = next(
        item for item in equipment_list if item.category == EquipmentCategory.REFRIGERATION.value
    )
    claim = session.execute(
        select(Claim).where(Claim.reference == "DEMO-000001")
    ).scalar_one_or_none()
    if claim is None:
        claim = Claim(
            id=uuid.uuid4(),
            reference="DEMO-000001",
            business_id=business.id,
            policy_id=policy.id,
            equipment_id=refrigerator.id,
            status=ClaimStatus.SUBMITTED.value,
            incident_date=date(2026, 10, 1),
            incident_description="Refrigerator stopped cooling overnight; stock may be affected.",
            amount_claimed=Decimal("800.00"),
        )
        session.add(claim)
        session.flush()

        # claim_events is append-only, so the event is written only with a new claim.
        owner_user = users["cafe.owner@equipsure.demo"]
        session.add(
            ClaimEvent(
                claim_id=claim.id,
                old_status=None,
                new_status=ClaimStatus.SUBMITTED.value,
                source=EventSource.POLICYHOLDER.value,
                actor_user_id=owner_user.id,
                explanation="Claim submitted by policyholder.",
            )
        )
        print("claim: created")
        return claim
    print("claim: exists")
    return claim


def main() -> None:
    url = settings.database_url
    check_not_test_database(url)
    passwords = read_seed_passwords()
    engine = create_engine(url, pool_pre_ping=True)
    print(f"Seed guard passed. Target: {settings.postgres_db}. Passwords loaded: {len(passwords)}.")

    try:
        # The with-block rolls back automatically if an exception escapes before commit.
        with Session(engine) as session:
            business = seed_business(session)
            users = seed_users(session, passwords, business)
            equipment_list = seed_equipment(session, business)
            policy = seed_policy(session, business)
            seed_policy_equipment(session, policy, equipment_list)
            seed_billing(session, policy)
            seed_claim(session, business, policy, equipment_list, users)
            session.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()