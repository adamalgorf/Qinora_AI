import re

import pytest
from fastapi.testclient import TestClient

from qinora.application.read_models import (
    OutboundReplyRecord,
    QuoteDocumentRecord,
    QuoteLineItemRecord,
    QuoteRecord,
    RequestCargoLineRecord,
    RequestDetailRecord,
    RequestRecord,
)
from qinora.infrastructure.quote_pdf import quote_filename, quote_reference, render_quote_pdf
from qinora.interfaces.http.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "false")
    return TestClient(create_app())


def _document(**quote_overrides) -> QuoteDocumentRecord:
    quote = QuoteRecord(
        **{
            "id": "7f3c2a10-0000-0000-0000-000000000000",
            "status": "sent",
            "version": 2,
            "customer_price": 18400.0,
            "currency": "SEK",
            "parent_quote_id": None,
            "request_id": "req-1",
            "customer": "Åkeri Öst AB",
            "lane": "Göteborg -> Hamburg",
            "carrier_name": "Nordic Freight",
            **quote_overrides,
        }
    )
    return QuoteDocumentRecord(
        quote=quote,
        line_items=(QuoteLineItemRecord("li-1", quote.id, "Freight charge", 18400.0, "SEK"),),
        acceptance_events=(),
        request=RequestDetailRecord(
            request=RequestRecord(
                id="req-1",
                public_id="REQ-2041",
                customer="Åkeri Öst AB",
                lane="Göteborg -> Hamburg",
                mode="ftl",
                status="quoted",
                weight_kg=680,
            ),
            review_reason=None,
            created_at="2026-09-18T10:00:00",
            cargo_lines=(
                RequestCargoLineRecord(
                    "c-1", "Pallar med reservdelar (ömtåligt)", 4, 680, 120, 80, 150, True, "1203"
                ),
            ),
        ),
        sent_email=OutboundReplyRecord(
            id="out-1",
            quote_id=quote.id,
            recipient="logistik@akeri.example",
            subject="Din offert",
            body_text="Hej!",
            status="sent",
            created_at="2026-09-18T10:05:00",
            sent_at="2026-09-18T10:06:00",
        ),
    )


def _assert_valid_pdf_structure(pdf: bytes) -> None:
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    xref_offset = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    assert pdf[xref_offset:].startswith(b"xref")
    offsets = re.findall(rb"(\d{10}) 00000 n ", pdf)
    for number, offset in enumerate(offsets, start=1):
        assert pdf[int(offset):].startswith(b"%d 0 obj" % number)


def test_render_quote_pdf_is_structurally_valid_and_customer_facing() -> None:
    pdf = render_quote_pdf(_document())

    _assert_valid_pdf_structure(pdf)
    # Swedish characters are encoded as WinAnsi (cp1252) bytes.
    assert "Åkeri Öst AB".encode("cp1252") in pdf
    assert b"REQ-2041-V2" in pdf
    assert "18 400,00 SEK".encode("cp1252") in pdf
    assert b"Frakt" in pdf
    assert b"UN 1203" in pdf
    assert b"2026-09-25" in pdf  # valid 7 days from the sent date
    # The carrier is internal - never printed on the customer's offer.
    assert b"Nordic Freight" not in pdf
    assert b"UTKAST" not in pdf


def test_unsent_quote_is_marked_as_draft() -> None:
    assert b"UTKAST" in render_quote_pdf(_document(status="draft"))


def test_long_quote_breaks_onto_several_pages() -> None:
    document = _document()
    many_lines = tuple(
        QuoteLineItemRecord(f"li-{i}", document.quote.id, f"Tillägg {i}", 100.0, "SEK")
        for i in range(80)
    )
    document = QuoteDocumentRecord(
        quote=QuoteRecord(**{**document.quote.__dict__, "customer_price": 8000.0}),
        line_items=many_lines,
        acceptance_events=(),
        request=document.request,
        sent_email=document.sent_email,
    )

    pdf = render_quote_pdf(document)

    _assert_valid_pdf_structure(pdf)
    assert b"/Count 3" in pdf or b"/Count 2" in pdf


def test_quote_reference_and_filename() -> None:
    document = _document()
    assert quote_reference(document) == "REQ-2041-V2"
    assert quote_filename(document) == "Offert-REQ-2041-V2-Åkeri-Öst-AB.pdf"


def test_quote_detail_and_pdf_endpoints(client: TestClient) -> None:
    quotes = client.get("/quotes").json()
    quote = next(item for item in quotes if item["request_id"])

    detail = client.get(f"/quotes/{quote['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["quote"]["customer"] == quote["customer"]
    assert body["reference"].endswith(f"-V{quote['version']}")
    assert body["request"]["request"]["id"] == quote["request_id"]

    pdf = client.get(f"/quotes/{quote['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf.headers["content-disposition"]
    _assert_valid_pdf_structure(pdf.content)


def test_quote_pdf_404_for_unknown_quote(client: TestClient) -> None:
    assert client.get("/quotes/does-not-exist/pdf").status_code == 404
