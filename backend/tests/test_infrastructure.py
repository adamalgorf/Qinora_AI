from pathlib import Path

import anyio
import pytest

from qinora.infrastructure.migrations import iter_migration_files
from qinora.infrastructure.settings import LLMProvider, PersistenceDriver, Settings
from qinora.infrastructure.sqlite import (
    SQLiteCaseNoteRepository,
    SQLiteDatabase,
    SQLiteDocumentRepository,
    SQLiteOperationalReadRepository,
)
from qinora.interfaces.http.container import build_container

# The new repository methods below (DocumentRepository, CaseNoteRepository,
# get_contact_detail, and the RequestRecord case-view fields) are exercised
# against the SQLite adapter only. This repo has no real-database-backed
# Postgres test harness to extend - see test_carrier_rfq.py's module
# docstring, which documents the same gap for CarrierRfqRepository - so
# there's no live Postgres available in this environment to run the
# PostgresDocumentRepository/PostgresCaseNoteRepository/
# get_contact_detail equivalents against. Both adapters were still
# implemented and manually smoke-tested through the FastAPI routers during
# development; this suite covers the SQLite side that CI/local runs
# actually execute.


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
        customer_mailbox=None,
        carrier_mailbox=None,
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


def test_document_repository_round_trips_through_sqlite(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "documents.sqlite3")
    documents = SQLiteDocumentRepository(database)
    reads = SQLiteOperationalReadRepository(database)

    async def scenario():
        created = await documents.create_document(
            filename="pod.pdf",
            content_type="application/pdf",
            size_bytes=3,
            content=b"pdf",
            document_type="pod",
            status="validated",
            ai_confidence=0.99,
            extracted_fields={"reference": "REQ-0001"},
            request_id="req-001",
            shipment_id=None,
            contact_id=None,
            uploaded_by="tester",
        )
        listed = await reads.list_documents()
        detail = await documents.get_document(created.id)
        content = await documents.get_document_content(created.id)
        missing = await documents.get_document("does-not-exist")
        return created, listed, detail, content, missing

    created, listed, detail, content, missing = anyio.run(scenario)

    assert created.public_id.startswith("DOC-")
    assert created.status == "validated"
    assert created.request_id == "req-001"

    assert any(item.id == created.id for item in listed)

    assert detail is not None
    assert detail.document.id == created.id
    assert detail.extracted_fields == {"reference": "REQ-0001"}

    assert content is not None
    assert content.filename == "pod.pdf"
    assert content.content_type == "application/pdf"
    assert content.content == b"pdf"

    assert missing is None


def test_case_note_repository_round_trips_through_sqlite(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "case_notes.sqlite3")
    notes = SQLiteCaseNoteRepository(database)
    reads = SQLiteOperationalReadRepository(database)

    async def scenario():
        created = await notes.create_note("req-001", author="Ada", body_text="Called customer")
        listed = await reads.list_case_notes("req-001")
        listed_other_request = await reads.list_case_notes("req-002")
        return created, listed, listed_other_request

    created, listed, listed_other_request = anyio.run(scenario)

    assert created.request_id == "req-001"
    assert created.author == "Ada"
    assert created.body_text == "Called customer"

    assert [note.id for note in listed] == [created.id]
    assert listed_other_request == []


def test_get_contact_detail_matches_shipments_by_customer_name(tmp_path: Path) -> None:
    # The seeded demo data (SQLiteDatabase._seed*) links req-001/Volvo Parts
    # through quo-003 to shp-001 (status "booked"), and the seeded contact
    # cnt-001 is "Volvo Parts" - this exercises the customer-name fallback
    # join documented on ContactDetailRecord (no adapter here ever
    # populates a contact_id FK on transport_requests).
    database = SQLiteDatabase(tmp_path / "contact_detail.sqlite3")
    reads = SQLiteOperationalReadRepository(database)

    async def scenario():
        detail = await reads.get_contact_detail("cnt-001")
        missing = await reads.get_contact_detail("does-not-exist")
        return detail, missing

    detail, missing = anyio.run(scenario)

    assert detail is not None
    assert detail.contact.display_name == "Volvo Parts"
    assert detail.active_jobs == 1
    assert detail.active_route == "Gothenburg -> Hamburg"
    # No inbound email is threaded to req-001 in the seed data, so this must
    # stay None rather than a fabricated number.
    assert detail.avg_ai_response_minutes is None

    assert missing is None


def test_request_record_case_fields_default_and_round_trip(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "request_case_fields.sqlite3")
    reads = SQLiteOperationalReadRepository(database)

    async def scenario():
        requests = await reads.list_requests()
        detail = await reads.get_request_detail("req-001")
        return requests, detail

    requests, detail = anyio.run(scenario)

    assert requests
    for request in requests:
        assert request.priority == "normal"
        assert request.assignee is None
        assert request.sla_due_at is None

    assert detail is not None
    assert detail.request.priority == "normal"
    assert detail.request.assignee is None
    assert detail.request.sla_due_at is None
