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
