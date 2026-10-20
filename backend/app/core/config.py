from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    ai_provider: str = "fake"
    gemini_api_key: str = ""

    postgres_user: str = "equipsure"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "equipsure"
    test_postgres_db: str = "equipsure_test"

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    storage_dir: str = "storage"
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_upload_types: str = "application/pdf,image/jpeg,image/png"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        # SQLAlchemy 2.x str(URL) redacts the password as "***"; render explicitly.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def test_database_url(self) -> str:
        # SQLAlchemy 2.x str(URL) redacts the password as "***"; render explicitly.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.test_postgres_db,
        ).render_as_string(hide_password=False)

    def assert_secure_for_environment(self) -> None:
        # Refuse to run outside development with a missing or placeholder JWT secret.
        # Wired into app startup in Phase 4b.
        if self.app_env == "development":
            return
        if not self.jwt_secret or self.jwt_secret.startswith("change"):
            raise RuntimeError(
                "JWT_SECRET must be set to a strong value outside development."
            )


settings = Settings()