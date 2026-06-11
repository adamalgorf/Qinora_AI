import hmac
from hashlib import sha256

from fastapi.testclient import TestClient

from qinora.interfaces.http.app import create_app


def test_email_webhook_requires_valid_hmac(monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "secret")
    client = TestClient(create_app())

    response = client.post(
        "/webhooks/email",
        headers={"x-idempotency-key": "email-1", "x-qinora-signature": "bad"},
        json={"sender": "shipper@example.com", "subject": "Quote", "body_text": "Need pickup"},
    )

    assert response.status_code == 401


def test_email_webhook_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "secret")
    client = TestClient(create_app())
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


def test_dashboard_summary_returns_control_tower_data() -> None:
    client = TestClient(create_app())

    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["kpis"][0]["label"] == "Open requests"


def test_core_module_endpoints_return_seeded_records() -> None:
    client = TestClient(create_app())

    assert client.get("/requests").json()[0]["public_id"] == "REQ-0001"
    assert client.get("/quotes").json()[0]["currency"] == "SEK"
    assert client.get("/shipments").json()[0]["public_id"] == "SHP-0001"
    assert client.get("/carriers").json()[0]["display_name"] == "Nordic Freight"
    assert client.get("/inbox/pending").json()[0]["classification"] == "transport_request"
    assert client.get("/agents/logs").json()[0]["agent_name"] == "Nora Intake"


def test_carrier_intelligence_endpoint_runs_domain_pipeline() -> None:
    client = TestClient(create_app())

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
