import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PersistenceDriver(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class LLMProvider(StrEnum):
    STUB = "stub"
    OPENAI = "openai"


@dataclass(frozen=True)
class Settings:
    email_webhook_secret: str
    sqlite_path: Path
    auth_token_secret: str
    persistence_driver: PersistenceDriver
    database_url: str | None
    postgres_tenant_id: str
    cors_allowed_origins: tuple[str, ...]
    app_password: str | None
    llm_provider: LLMProvider
    openai_api_key: str | None
    openai_model: str
    default_markup_percent: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            email_webhook_secret=os.getenv("EMAIL_WEBHOOK_SECRET", "dev-secret"),
            sqlite_path=Path(os.getenv("QINORA_SQLITE_PATH", "data/qinora.dev.sqlite3")),
            auth_token_secret=os.getenv("QINORA_AUTH_TOKEN_SECRET", "dev-auth-secret"),
            persistence_driver=PersistenceDriver(os.getenv("QINORA_PERSISTENCE", "sqlite")),
            database_url=os.getenv("DATABASE_URL"),
            postgres_tenant_id=os.getenv(
                "QINORA_POSTGRES_TENANT_ID",
                "00000000-0000-0000-0000-000000000001",
            ),
            cors_allowed_origins=tuple(
                origin.strip()
                for origin in os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
                if origin.strip()
            ),
            app_password=os.getenv("QINORA_APP_PASSWORD") or None,
            llm_provider=LLMProvider(os.getenv("LLM_PROVIDER", "stub")),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            default_markup_percent=float(os.getenv("QINORA_DEFAULT_MARKUP_PERCENT", "15")),
        )
