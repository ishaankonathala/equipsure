from sqlalchemy import text


def test_test_database_is_migrated(session):
    version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0002"