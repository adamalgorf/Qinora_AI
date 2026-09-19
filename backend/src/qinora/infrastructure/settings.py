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
    require_auth: bool
    llm_provider: LLMProvider
    openai_api_key: str | None
    openai_model: str
    default_markup_percent: float
    customer_mailbox: str | None
    carrier_mailbox: str | None
    # Used to rank knowledge-base excerpts (application/knowledge.py).
    openai_embedding_model: str = "text-embedding-3-small"

    @classmethod
    def from_env(cls) -> "Settings":
        persistence_driver = PersistenceDriver(os.getenv("QINORA_PERSISTENCE", "sqlite"))
        require_auth_override = os.getenv("QINORA_REQUIRE_AUTH")
        require_auth = (
            _parse_bool(require_auth_override)
            if require_auth_override is not None
            else persistence_driver is PersistenceDriver.POSTGRES
        )
        return cls(
            email_webhook_secret=os.getenv("EMAIL_WEBHOOK_SECRET", "dev-secret"),
            sqlite_path=Path(os.getenv("QINORA_SQLITE_PATH", "data/qinora.dev.sqlite3")),
            auth_token_secret=os.getenv("QINORA_AUTH_TOKEN_SECRET", "dev-auth-secret"),
            persistence_driver=persistence_driver,
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
            require_auth=require_auth,
            llm_provider=LLMProvider(os.getenv("LLM_PROVIDER", "stub")),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            default_markup_percent=float(os.getenv("QINORA_DEFAULT_MARKUP_PERCENT", "10")),
            # Which mailbox each outbound queue's items should be sent from,
            # when more than one mailbox/bridge instance is in play (see
            # workers/outlook_bridge.py) - e.g. customer-facing quotes from
            # test.spedition@sandahls.com, carrier RFQs from
            # qinora.ai@sandahls.com. Unset (the single-mailbox default)
            # means "any bridge instance may send it".
            customer_mailbox=os.getenv("QINORA_CUSTOMER_MAILBOX") or None,
            carrier_mailbox=os.getenv("QINORA_CARRIER_MAILBOX") or None,
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
        )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
