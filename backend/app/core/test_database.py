from app.core.config import settings


def get_test_database_url() -> str:
    if settings.test_postgres_db == settings.postgres_db:
        raise RuntimeError("Tests must not use the development database.")
    if not settings.test_postgres_db.endswith("_test"):
        raise RuntimeError("Tests must not use the development database.")
    return settings.test_database_url
