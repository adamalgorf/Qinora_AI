import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    email_webhook_secret: str
    sqlite_path: Path
    auth_token_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            email_webhook_secret=os.getenv("EMAIL_WEBHOOK_SECRET", "dev-secret"),
            sqlite_path=Path(os.getenv("QINORA_SQLITE_PATH", "data/qinora.dev.sqlite3")),
            auth_token_secret=os.getenv("QINORA_AUTH_TOKEN_SECRET", "dev-auth-secret"),
        )
