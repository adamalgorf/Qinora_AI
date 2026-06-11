import hmac
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from qinora.interfaces.http.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora.test.sqlite3"))
    return TestClient(create_app())


def test_email_webhook_requires_valid_hmac(client: TestClient) -> None:
    response = client.post(
        "/webhooks/email",
        headers={"x-idempotency-key": "email-1", "x-qinora-signature": "bad"},
        json={"sender": "shipper@example.com", "subject": "Quote", "body_text": "Need pickup"},
    )

    assert response.status_code == 401


def test_email_webhook_is_idempotent(client: TestClient) -> None:
    payload = b'{"sender":"shipper@example.com","subject":"Quote","body_text":"Need pickup"}'
    signature = hmac.new(b"secret", payload, sha256).hexdigest()
    headers = {
        "content-type": "application/json",
        "x-idempotency-key": "email-1",
        "x-qinora-signature": f"sha256={signature}",
    }

    first = client.post("/webhooks/email", headers=headers, content=payload)
    second = client.post("/webhooks/email", headers=headers, content=payload)

    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert second.status_code == 202
    assert second.json()["duplicate"] is True


def test_dashboard_summary_returns_control_tower_data(client: TestClient) -> None:
    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["kpis"][0]["label"] == "Open requests"


def test_auth_me_returns_server_side_context(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers={
            "x-user-id": "user-1",
            "x-tenant-id": "tenant-1",
            "x-role": "4pl_tower,admin",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "tenant_id": "tenant-1",
        "roles": ["4pl_tower", "admin"],
    }


def test_core_module_endpoints_return_seeded_records(client: TestClient) -> None:
    assert client.get("/requests").json()[0]["public_id"] == "REQ-0001"
    assert client.get("/quotes").json()[0]["currency"] == "SEK"
    assert client.get("/shipments").json()[0]["public_id"] == "SHP-0001"
    carrier_names = {carrier["display_name"] for carrier in client.get("/carriers").json()}
    assert "Nordic Freight" in carrier_names
    assert client.get("/inbox/pending").json()[0]["classification"] == "transport_request"
    assert client.get("/agents/logs").json()[0]["agent_name"] == "Nora Intake"


def test_create_request_persists_complete_request(client: TestClient) -> None:
    response = client.post(
        "/requests",
        json={
            "customer": "Scania",
            "origin": "Sodertalje",
            "destination": "Berlin",
            "mode": "ltl",
            "loading_time": "2026-06-11T10:00:00Z",
            "cargo": [
                {
                    "description": "Pallets",
                    "quantity": 2,
                    "weight_kg": 440,
                    "length_cm": 120,
                    "width_cm": 80,
                    "height_cm": 150,
                }
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["complete"] is True
    assert body["request"]["status"] == "parsed"
    assert body["request"]["customer"] == "Scania"


def test_create_request_marks_incomplete_request_for_clarification(client: TestClient) -> None:
    response = client.post(
        "/requests",
        json={
            "customer": "Scania",
            "origin": "Sodertalje",
            "destination": "Berlin",
            "mode": "ltl",
            "cargo": [{"description": "Paint UN1263"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["complete"] is False
    assert body["request"]["status"] == "needs_clarification"
    assert body["adr_un_numbers"] == ["UN1263"]


def test_carrier_intelligence_endpoint_runs_domain_pipeline(client: TestClient) -> None:
    response = client.post(
        "/carriers/intelligence",
        json={
            "mode": "ftl",
            "total_weight_kg": 500,
            "requested_carrier_name": "Nordic",
        },
    )

    assert response.status_code == 200
    assert response.json()["selected_carrier_id"] == "car-001"


def test_carrier_intelligence_requires_operator_role(client: TestClient) -> None:
    response = client.post(
        "/carriers/intelligence",
        headers={"x-role": "shipper"},
        json={
            "mode": "ftl",
            "total_weight_kg": 500,
            "requested_carrier_name": "Nordic",
        },
    )

    assert response.status_code == 403
