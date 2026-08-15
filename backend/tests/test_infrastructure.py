from pathlib import Path

import pytest

from qinora.infrastructure.migrations import iter_migration_files
from qinora.infrastructure.settings import LLMProvider, PersistenceDriver, Settings
from qinora.interfaces.http.container import build_container


def test_settings_selects_postgres_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QINORA_PERSISTENCE", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/qinora")
    monkeypatch.setenv("QINORA_POSTGRES_TENANT_ID", "11111111-1111-1111-1111-111111111111")

    settings = Settings.from_env()

    assert settings.persistence_driver is PersistenceDriver.POSTGRES
    assert settings.database_url == "postgres://postgres:postgres@localhost:5432/qinora"
    assert settings.postgres_tenant_id == "11111111-1111-1111-1111-111111111111"


def test_postgres_container_requires_database_url(tmp_path: Path) -> None:
    settings = Settings(
        email_webhook_secret="secret",
        sqlite_path=tmp_path / "qinora.sqlite3",
        auth_token_secret="auth-secret",
        persistence_driver=PersistenceDriver.POSTGRES,
        database_url=None,
        postgres_tenant_id="11111111-1111-1111-1111-111111111111",
        cors_allowed_origins=("*",),
        app_password=None,
        llm_provider=LLMProvider.STUB,
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        default_markup_percent=15.0,
    )

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        build_container(settings)


def test_iter_migration_files_returns_sorted_sql_files(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("select 2;", encoding="utf-8")
    (tmp_path / "notes.md").write_text("skip", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("select 1;", encoding="utf-8")

    assert [file.name for file in iter_migration_files(tmp_path)] == [
        "0001_first.sql",
        "0002_second.sql",
    ]
