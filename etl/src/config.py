from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


class Settings:
    # Database
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "leipzig_data")
    postgres_user: str = os.getenv("POSTGRES_USER", "leipzig")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Leipzig APIs
    api_base: str = os.getenv("LEIPZIG_API_BASE", "https://opendata.leipzig.de/api/3")
    stat_api_base: str = os.getenv(
        "LEIPZIG_STAT_API_BASE", "https://statistik.leipzig.de/opendata/api"
    )

    # ETL behaviour
    request_timeout: int = int(os.getenv("ETL_REQUEST_TIMEOUT_SECONDS", "60"))
    max_retries: int = int(os.getenv("ETL_MAX_RETRIES", "3"))
    backoff_factor: float = float(os.getenv("ETL_BACKOFF_FACTOR", "2.0"))
    live_interval: int = int(os.getenv("ETL_LIVE_INTERVAL_SECONDS", "300"))
    nightly_cron: str = os.getenv("ETL_NIGHTLY_CRON", "0 2 * * *")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Paths
    contracts_path: Path = Path(__file__).parent.parent / "dataset_contracts.json"
    families_path: Path = Path(
        os.getenv("ETL_FAMILIES_PATH")
        or Path(__file__).parent.parent / "dataset_families.json"
    )
    categories_path: Path = Path(
        os.getenv("ETL_CATEGORIES_PATH")
        or Path(__file__).parent.parent / "dataset_categories.json"
    )
    elections_path: Path = Path(
        os.getenv("ETL_ELECTIONS_PATH")
        or Path(__file__).parent.parent / "election_definitions.json"
    )
    logs_dir: Path = Path(os.getenv("ETL_LOGS_DIR", "/app/logs"))


settings = Settings()
