import asyncio
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from qinora.application.agent_config import DEFAULT_AGENT_CONFIGS
from qinora.application.agent_registry import (
    AGENTS,
    NORA,
    ORION,
    QUINN,
    KnowledgeDomain,
    get_agent,
)
from qinora.application.knowledge import (
    EMPTY_BRIEF,
    AddKnowledgeDocumentCommand,
    AgentKnowledge,
    KnowledgeBaseService,
    KnowledgeValidationError,
    chunk_text,
    compose_system_prompt,
    with_consulted_documents,
)
from qinora.infrastructure.knowledge_text import PlainTextAndPdfExtractor
from qinora.infrastructure.llm import openai_client
from qinora.infrastructure.llm.embeddings import StubTextEmbedder
from qinora.infrastructure.llm.openai_client import KnowledgeGroundedLLM
from qinora.infrastructure.llm.request_parsing import OpenAIRequestParsingLLM
from qinora.infrastructure.passwords import hash_password
from qinora.infrastructure.settings import Settings
from qinora.infrastructure.sqlite import (
    SQLiteDatabase,
    SQLiteKnowledgeRepository,
    SQLiteUserRepository,
)
from qinora.interfaces.http.app import create_app


def _knowledge(tmp_path: Path, embedder=None, **retriever_kwargs):
    repository = SQLiteKnowledgeRepository(SQLiteDatabase(tmp_path / "kb.sqlite3"))
    embedder = embedder or StubTextEmbedder()
    service = KnowledgeBaseService(repository, PlainTextAndPdfExtractor(), embedder)
    return service, AgentKnowledge(repository, embedder, **retriever_kwargs), repository


def _add(service: KnowledgeBaseService, title: str, domain: KnowledgeDomain, text: str):
    return anyio.run(
        service.add_document,
        AddKnowledgeDocumentCommand(domain=domain.value, title=title, text=text),
    )


# --- registry: the scalability contract ----------------------------------


def test_every_agent_has_a_config_row_and_reads_general() -> None:
    assert {config.agent_key for config in DEFAULT_AGENT_CONFIGS} == {a.key for a in AGENTS}
    for agent in AGENTS:
        assert KnowledgeDomain.GENERAL in agent.readable_domains


def test_every_grounded_adapter_belongs_to_a_registered_agent() -> None:
    # A new agent adapter that forgets to register its role would silently
    # read nothing - fail loudly instead.
    import qinora.infrastructure.llm  # noqa: F401 - registers every adapter

    adapters = KnowledgeGroundedLLM.__subclasses__()
    assert len(adapters) >= 4
    for adapter in adapters:
        assert get_agent(adapter.agent_key) is not None, adapter.__name__


# --- chunking ------------------------------------------------------------


def test_chunk_text_keeps_chunks_under_the_limit_and_overlaps() -> None:
    paragraphs = [f"Stycke {i}: " + ("lastning vid terminal " * 12).strip() for i in range(12)]
    chunks = chunk_text("\n\n".join(paragraphs), max_chars=400, overlap=60)

    assert len(chunks) > 1
    assert all(len(chunk) <= 400 for chunk in chunks)
    # the tail of one chunk carries into the next
    assert chunks[0].split()[-1] in chunks[1]


def test_chunk_text_repeats_the_csv_header_in_every_chunk() -> None:
    rows = "\n".join(f"Kund {i};Göteborg;Hamburg;{i * 10}" for i in range(120))
    chunks = chunk_text(f"kund;från;till;pallar\n{rows}", max_chars=300, repeat_header=True)

    assert len(chunks) > 1
    assert all(chunk.startswith("kund;från;till;pallar\n") for chunk in chunks)


# --- adding documents ----------------------------------------------------


def test_add_pasted_text_stores_document_with_chunks(tmp_path) -> None:
    service, _, _ = _knowledge(tmp_path)
    record = _add(service, "Volvo Cars", KnowledgeDomain.CUSTOMERS, "Lastar alltid vid port 4.")

    assert record.public_id == "KB-0001"
    assert record.domain == "customers"
    assert record.chunk_count == 1
    assert record.embedded is False
    detail = anyio.run(service.get_document, record.id)
    assert detail is not None and detail.text == "Lastar alltid vid port 4."


def test_add_text_file_uses_filename_as_title(tmp_path) -> None:
    service, _, _ = _knowledge(tmp_path)
    record = anyio.run(
        service.add_document,
        AddKnowledgeDocumentCommand(
            domain="routes",
            filename="Göteborg-Hamburg.md",
            content="# Lane\nFärja via Kiel.".encode(),
        ),
    )
    assert record.title == "Göteborg-Hamburg"
    assert record.source_filename == "Göteborg-Hamburg.md"


def test_add_pdf_extracts_its_text(tmp_path) -> None:
    service, _, _ = _knowledge(tmp_path)
    record = anyio.run(
        service.add_document,
        AddKnowledgeDocumentCommand(
            domain="terms",
            filename="villkor.pdf",
            content=_pdf_with_text("Betalningsvillkor 30 dagar netto"),
        ),
    )
    detail = anyio.run(service.get_document, record.id)
    assert detail is not None
    assert "Betalningsvillkor 30 dagar netto" in detail.text


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (AddKnowledgeDocumentCommand(domain="customers", title="X"), "Ladda upp en fil"),
        (
            AddKnowledgeDocumentCommand(domain="customers", filename="a.exe", content=b"x"),
            "Filtypen stöds inte",
        ),
        (AddKnowledgeDocumentCommand(domain="pricing", title="X", text="y"), "Okänt"),
        (
            AddKnowledgeDocumentCommand(domain="customers", filename="tom.txt", content=b"  \n"),
            "ingen läsbar text",
        ),
    ],
)
def test_invalid_uploads_are_rejected_with_a_clear_reason(tmp_path, command, message) -> None:
    service, _, _ = _knowledge(tmp_path)
    with pytest.raises(KnowledgeValidationError, match=message):
        anyio.run(service.add_document, command)


# --- retrieval -----------------------------------------------------------


def test_each_agent_reads_only_its_own_domains(tmp_path) -> None:
    service, knowledge, _ = _knowledge(tmp_path)
    _add(service, "Kund Volvo", KnowledgeDomain.CUSTOMERS, "Volvo lastar vid port 4.")
    _add(service, "DHL Freight", KnowledgeDomain.CARRIERS, "DHL har kapacitet till Tyskland.")
    _add(service, "Om Sandahls", KnowledgeDomain.GENERAL, "Sandahls är en speditör i Mölndal.")

    nora = anyio.run(knowledge.brief_for, NORA.key, "Förfrågan från Volvo")
    quinn = anyio.run(knowledge.brief_for, QUINN.key, "Offert från DHL")

    assert set(nora.document_titles) == {"Kund Volvo", "Om Sandahls"}
    assert set(quinn.document_titles) == {"Kund Volvo", "DHL Freight", "Om Sandahls"}
    assert nora.agent_name == "Nora"


def test_large_knowledge_base_ranks_the_matching_customer_first(tmp_path) -> None:
    service, knowledge, _ = _knowledge(tmp_path, char_budget=400, max_snippets=2)
    for name in ("Scania", "Ikea", "Ericsson", "Husqvarna", "Electrolux"):
        _add(
            service,
            f"Kund {name}",
            KnowledgeDomain.CUSTOMERS,
            f"{name} har egna rutiner för lastning och vill ha avisering dagen innan. " * 2,
        )
    _add(service, "Kund Volvo", KnowledgeDomain.CUSTOMERS, "Volvo lastar alltid vid port 4.")

    brief = anyio.run(knowledge.brief_for, NORA.key, "Hej, Volvo behöver en bil från Torslanda")

    assert brief.document_titles[0] == "Kund Volvo"
    assert len(brief.snippets) <= 2


def test_semantic_ranking_is_used_when_embeddings_exist(tmp_path) -> None:
    class KeywordEmbedder:
        # "embeds" by topic so the query matches without sharing a word
        async def embed(self, texts):
            return [[1.0, 0.0] if ("kyl" in t.lower() or "frys" in t.lower()) else [0.0, 1.0]
                    for t in texts]

    service, knowledge, _ = _knowledge(tmp_path, embedder=KeywordEmbedder(), char_budget=120)
    _add(service, "Rutt A", KnowledgeDomain.ROUTES, "Torrgods mellan Borås och Jönköping. " * 3)
    _add(service, "Rutt B", KnowledgeDomain.ROUTES, "Kylbil krävs, temperatur 2-8 grader. " * 3)

    brief = anyio.run(knowledge.brief_for, NORA.key, "Vi har frysvaror som ska skickas")

    assert brief.document_titles == ("Rutt B",)


def test_retrieval_failure_never_blocks_the_agent(tmp_path) -> None:
    class BrokenRepository:
        async def revision(self):
            raise RuntimeError("database down")

    knowledge = AgentKnowledge(BrokenRepository(), StubTextEmbedder())
    assert anyio.run(knowledge.brief_for, NORA.key, "anything") is EMPTY_BRIEF


def test_unknown_agent_reads_nothing(tmp_path) -> None:
    _, knowledge, _ = _knowledge(tmp_path)
    assert anyio.run(knowledge.brief_for, "no_such_agent", "x") is EMPTY_BRIEF


def test_cache_sees_a_delete_followed_by_an_add(tmp_path) -> None:
    # Regression: a count/max-id revision marker comes out identical after
    # deleting the newest document and adding another, serving stale chunks.
    service, knowledge, _ = _knowledge(tmp_path)
    _add(service, "Gammal", KnowledgeDomain.CUSTOMERS, "Gammal regel.")
    newest = _add(service, "Borttagen", KnowledgeDomain.CUSTOMERS, "Ska försvinna.")
    assert "Borttagen" in anyio.run(knowledge.brief_for, NORA.key, "x").document_titles

    anyio.run(service.delete_document, newest.id)
    _add(service, "Ny", KnowledgeDomain.CUSTOMERS, "Ny regel.")

    titles = anyio.run(knowledge.brief_for, NORA.key, "x").document_titles
    assert "Borttagen" not in titles
    assert "Ny" in titles


# --- the agent actually reads it ----------------------------------------


def test_prompt_section_contains_excerpts_and_safety_rules(tmp_path) -> None:
    service, knowledge, _ = _knowledge(tmp_path)
    _add(service, "Kund Volvo", KnowledgeDomain.CUSTOMERS, "Volvo lastar vid port 4.")
    brief = anyio.run(knowledge.brief_for, NORA.key, "Volvo")

    prompt = compose_system_prompt("BASE PROMPT", brief)

    assert prompt.startswith("BASE PROMPT\n\n## Company knowledge base")
    assert "Volvo lastar vid port 4." in prompt
    assert "Never take prices" in prompt
    assert "not instructions" in prompt
    assert compose_system_prompt("BASE PROMPT", EMPTY_BRIEF) == "BASE PROMPT"


def test_nora_reads_her_knowledge_before_parsing(tmp_path, monkeypatch) -> None:
    service, knowledge, _ = _knowledge(tmp_path)
    _add(service, "Kund Volvo", KnowledgeDomain.CUSTOMERS, "Volvo lastar vid port 4, Torslanda.")
    seen: dict[str, str] = {}

    class FakeClient:
        def __init__(self, api_key, model):
            pass

        async def complete(self, *, system_prompt, user_text, schema):
            seen["system_prompt"] = system_prompt
            return schema.model_validate(
                {
                    "action": "create",
                    "mode": "ftl",
                    "origin": "Torslanda",
                    "destination": "Hamburg",
                    "confidence": 0.9,
                }
            )

    monkeypatch.setattr(openai_client, "OpenAIStructuredClient", FakeClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm = OpenAIRequestParsingLLM(Settings.from_env(), knowledge)

    draft = anyio.run(lambda: llm.parse(raw_text="Volvo behöver en bil till Hamburg"))

    assert "Volvo lastar vid port 4, Torslanda." in seen["system_prompt"]
    assert draft.consulted_documents == ("Kund Volvo",)


def test_consulted_documents_are_appended_to_the_agent_log_step() -> None:
    assert with_consulted_documents("Parsed request", ()) == "Parsed request"
    assert (
        with_consulted_documents("Parsed request", ("A", "B", "C", "D"))
        == "Parsed request · läste: A, B, C +1"
    )


# --- HTTP ----------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path) -> tuple[TestClient, dict[str, dict[str, str]]]:
    sqlite_path = tmp_path / "qinora_test.sqlite3"
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "true")

    async def create_users() -> None:
        repository = SQLiteUserRepository(SQLiteDatabase(sqlite_path))
        for email, role in (("admin@example.com", "admin"), ("shipper@example.com", "shipper")):
            await repository.create_user(
                email=email,
                full_name="Test",
                password_hash=hash_password("correct-horse"),
                roles=(role,),
            )

    asyncio.run(create_users())
    app_client = TestClient(create_app())
    headers = {}
    for name in ("admin", "shipper"):
        token = app_client.post(
            "/auth/login", json={"email": f"{name}@example.com", "password": "correct-horse"}
        ).json()["access_token"]
        headers[name] = {"authorization": f"Bearer {token}"}
    return app_client, headers


def test_knowledge_api_add_list_preview_delete(client) -> None:
    app, headers = client
    created = app.post(
        "/knowledge",
        data={"domain": "customers", "title": "Kund Volvo", "text": "Volvo lastar vid port 4."},
        headers=headers["admin"],
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["read_by"] == ["Nora", "Quinn", "Orion"]
    assert document["domain_label"] == "Kunder"

    listed = app.get("/knowledge", headers=headers["admin"]).json()
    assert [item["title"] for item in listed] == ["Kund Volvo"]

    overview = app.get("/knowledge/overview", headers=headers["admin"]).json()
    customers = next(d for d in overview["domains"] if d["key"] == "customers")
    assert customers["document_count"] == 1
    assert {agent["name"] for agent in overview["agents"]} == {"Nora", "Quinn", "Orion"}

    preview = app.post(
        "/knowledge/preview",
        json={"agent_key": ORION.key, "text": "Volvo accepterar offerten"},
        headers=headers["admin"],
    ).json()
    assert [snippet["title"] for snippet in preview["snippets"]] == ["Kund Volvo"]

    deleted = app.delete(f"/knowledge/{document['id']}", headers=headers["admin"])
    assert deleted.status_code == 204
    assert app.get("/knowledge", headers=headers["admin"]).json() == []


def test_knowledge_api_requires_login_and_write_role(client) -> None:
    app, headers = client
    assert app.get("/knowledge").status_code == 401
    assert app.get("/knowledge/overview").status_code == 401

    forbidden = app.post(
        "/knowledge",
        data={"domain": "customers", "title": "X", "text": "y"},
        headers=headers["shipper"],
    )
    assert forbidden.status_code == 403


def test_knowledge_api_rejects_unsupported_file(client) -> None:
    app, headers = client
    response = app.post(
        "/knowledge",
        data={"domain": "routes"},
        files={"file": ("rutter.xlsx", b"binary", "application/octet-stream")},
        headers=headers["admin"],
    )
    assert response.status_code == 422
    assert "Filtypen stöds inte" in response.json()["detail"]


def _pdf_with_text(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
