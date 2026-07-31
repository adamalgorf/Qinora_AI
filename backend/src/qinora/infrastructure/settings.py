import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PersistenceDriver(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class LLMProvider(StrEnum):
    """Which backend implements the LLM-facing ports (e.g. RequestParsingLLM).

    STUB requires no credentials and is the default so the app keeps
    working out of the box. Switch to AZURE_OPENAI once real Azure OpenAI
    credentials are available (see AZURE_OPENAI_* below).
    """

    STUB = "stub"
    AZURE_OPENAI = "azure_openai"


@dataclass(frozen=True)
class Settings:
    email_webhook_secret: str
    sqlite_path: Path
    auth_token_secret: str
    persistence_driver: PersistenceDriver
    database_url: str | None
    postgres_tenant_id: str
    llm_provider: LLMProvider
    azure_openai_endpoint: str | None
    azure_openai_api_key: str | None
    azure_openai_deployment: str | None
    azure_openai_api_version: str

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
            llm_provider=LLMProvider(os.getenv("LLM_PROVIDER", "stub")),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
