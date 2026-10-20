import os
import sys

from sqlalchemy import create_engine

from app.core.config import settings

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


def main() -> None:
    url = settings.database_url
    check_not_test_database(url)
    passwords = read_seed_passwords()
    engine = create_engine(url, pool_pre_ping=True)
    print(f"Seed guard passed. Target: {settings.postgres_db}. Passwords loaded: {len(passwords)}.")
    engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
