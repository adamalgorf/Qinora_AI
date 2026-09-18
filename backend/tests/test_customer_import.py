import asyncio

import pytest
from fastapi.testclient import TestClient

from qinora.application.customer_import import (
    CustomerInput,
    CustomerValidationError,
    normalize_customer_input,
    parse_customer_csv,
)
from qinora.infrastructure.sqlite import SQLiteContactReadRepository
from qinora.interfaces.http.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "false")
    return TestClient(create_app())


def test_domain_is_derived_from_company_email() -> None:
    customer = normalize_customer_input(
        CustomerInput(display_name="  Scania  ", email="Logistik@Scania.SE")
    )
    assert customer.display_name == "Scania"
    assert customer.email == "logistik@scania.se"
    assert customer.domain == "scania.se"


def test_domain_is_not_derived_from_public_webmail() -> None:
    customer = normalize_customer_input(
        CustomerInput(display_name="Enskild firma", email="nisse@gmail.com")
    )
    assert customer.domain is None


def test_public_webmail_domain_is_rejected_explicitly() -> None:
    with pytest.raises(CustomerValidationError):
        normalize_customer_input(CustomerInput(display_name="X", domain="gmail.com"))


def test_parse_semicolon_csv_with_swedish_headers_and_numbers() -> None:
    content = (
        "Kundnamn;E-post;Påslag;SLA;Årlig volym;Hälsa;Kund sedan\n"
        "Scania;logistik@scania.se;12,5;48;1 250 000,50;bevaka;2024-03-01\n"
        ";\n"
        "Trasig;inte-en-mail;x;;;;\n"
    ).encode("cp1252")

    rows, issues = parse_customer_csv(content)

    assert [row_number for row_number, _ in rows] == [2]
    first = rows[0][1]
    assert first.display_name == "Scania"
    assert first.default_markup_percent == 12.5
    assert first.sla_tolerance_hours == 48
    assert first.annual_volume_estimate == 1250000.5
    assert issues[0].row == 4
    assert "Påslag" in issues[0].reason


def test_parse_requires_a_name_column() -> None:
    with pytest.raises(CustomerValidationError):
        parse_customer_csv(b"email,phone\na@b.se,123\n")


def test_create_contact_endpoint_adds_customer_to_list(client: TestClient) -> None:
    response = client.post(
        "/contacts",
        json={"display_name": "Scania", "email": "logistik@scania.se", "health_status": "watch"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["domain"] == "scania.se"
    assert created["public_id"].startswith("CNT-")

    names = [item["display_name"] for item in client.get("/contacts").json()]
    assert "Scania" in names

    detail = client.get(f"/contacts/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["health_status"] == "watch"


def test_create_contact_rejects_duplicate(client: TestClient) -> None:
    assert client.post("/contacts", json={"display_name": "Scania"}).status_code == 201
    duplicate = client.post("/contacts", json={"display_name": "scania"})
    assert duplicate.status_code == 422


def test_created_contact_is_matched_on_inbound_sender(client: TestClient) -> None:
    client.post("/contacts", json={"display_name": "Scania", "email": "logistik@scania.se"})
    repository = SQLiteContactReadRepository(client.app.state.container.database)
    contact = asyncio.run(repository.find_by_sender("someone.else@scania.se"))
    assert contact is not None
    assert contact.display_name == "Scania"


def test_import_endpoint_creates_skips_and_reports(client: TestClient) -> None:
    client.post("/contacts", json={"display_name": "Scania", "email": "logistik@scania.se"})
    csv_content = (
        "name,email,incoterms\n"
        "Scania AB,logistik@scania.se,dap\n"
        "Ikea Supply,transport@ikea.example,fca\n"
        "Ikea Supply,other@ikea.example,fca\n"
        ",missing@name.example,\n"
    )

    response = client.post(
        "/contacts/import",
        files={"file": ("kunder.csv", csv_content.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["display_name"] for item in body["created"]] == ["Ikea Supply"]
    assert body["created"][0]["default_incoterms"] == "FCA"
    assert [issue["row"] for issue in body["skipped"]] == [2, 4]
    assert [issue["row"] for issue in body["errors"]] == [5]


def test_import_endpoint_rejects_file_without_name_column(client: TestClient) -> None:
    response = client.post(
        "/contacts/import",
        files={"file": ("kunder.csv", b"email\na@b.se\n", "text/csv")},
    )
    assert response.status_code == 422
