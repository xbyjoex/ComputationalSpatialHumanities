from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "leipzig_data"
    postgres_user: str = "leipzig"
    postgres_password: str = ""

    # Auth
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Telegram (registration approval; same bot/chat as the ETL notifier)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
