import hmac
from hashlib import sha256

import anyio
import pytest
from fastapi.testclient import TestClient

from qinora.application import EscalateStaleRequestsCommand
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


def test_email_webhook_matches_sender_to_crm_contact(client: TestClient) -> None:
    payload = b'{"sender":"logistics@volvo.example","subject":"Quote","body_text":"Need pickup"}'
    signature = hmac.new(b"secret", payload, sha256).hexdigest()

    response = client.post(
        "/webhooks/email",
        headers={
            "content-type": "application/json",
            "x-idempotency-key": "email-crm-1",
            "x-qinora-signature": f"sha256={signature}",
        },
        content=payload,
    )

    assert response.status_code == 202
    logs = client.get("/agents/logs").json()
    match_log = next(item for item in logs if item["agent_key"] == "customer_match_agent")
    assert match_log["agent_name"] == "Miles Match"
    assert match_log["entity_id"] == "CNT-0001"
    assert "Volvo Parts" in match_log["step"]


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


def test_auth_dev_token_can_authorize_me_request(client: TestClient) -> None:
    token_response = client.post(
        "/auth/dev-token",
        json={"user_id": "user-2", "tenant_id": "tenant-2", "roles": ["4pl_tower"]},
    )

    assert token_response.status_code == 200

    response = client.get(
        "/auth/me",
        headers={"authorization": f"Bearer {token_response.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-2",
        "tenant_id": "tenant-2",
        "roles": ["4pl_tower"],
    }


def test_auth_me_rejects_tampered_bearer_token(client: TestClient) -> None:
    token_response = client.post(
        "/auth/dev-token",
        json={"user_id": "user-2", "tenant_id": "tenant-2", "roles": ["admin"]},
    )
    token = token_response.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"authorization": f"Bearer {token[:-1]}x"},
    )

    assert response.status_code == 401


def test_core_module_endpoints_return_seeded_records(client: TestClient) -> None:
    assert client.get("/requests").json()[0]["public_id"] == "REQ-0001"
    assert client.get("/quotes").json()[0]["currency"] == "SEK"
    assert client.get("/shipments").json()[0]["public_id"] == "SHP-0001"
    assert client.get("/contacts").json()[0]["public_id"] == "CNT-0003"
    carrier_names = {carrier["display_name"] for carrier in client.get("/carriers").json()}
    assert "Nordic Freight" in carrier_names
    assert client.get("/inbox/pending").json()[0]["classification"] == "transport_request"
    assert client.get("/agents/logs").json()[0]["agent_name"] == "Nora Intake"


def test_global_search_returns_deep_links_across_entities(client: TestClient) -> None:
    response = client.get("/search", params={"q": "volvo"})

    assert response.status_code == 200
    results = response.json()
    assert any(
        item["entity_type"] == "request" and item["href"] == "/requests?highlight=req-001"
        for item in results
    )
    assert any(
        item["entity_type"] == "contact" and item["href"] == "/contacts?highlight=cnt-001"
        for item in results
    )

    shipment_response = client.get("/search", params={"q": "SHP-0001"})
    assert shipment_response.status_code == 200
    assert shipment_response.json()[0]["href"] == "/shipments?highlight=shp-001"


def test_global_search_requires_operator_role(client: TestClient) -> None:
    response = client.get("/search", params={"q": "volvo"}, headers={"x-role": "shipper"})

    assert response.status_code == 403


def test_demo_flow_runs_order_to_cash_workflow(client: TestClient) -> None:
    response = client.post("/demo/flow")

    assert response.status_code == 200
    body = response.json()
    assert body["steps"][-1] == "Invoice audited and approved"
    assert body["request"]["status"] == "parsed"
    assert body["quote"]["status"] == "sent"
    assert body["outbound_reply"]["status"] == "sent"
    assert body["shipment"]["status"] == "booked"
    assert body["invoice"]["status"] == "approved"
    assert body["shipment_status"] == "invoice_approved"

    shipments = client.get("/shipments").json()
    completed_shipment = next(item for item in shipments if item["id"] == body["shipment"]["id"])
    assert completed_shipment["status"] == "invoice_approved"


def test_demo_flow_requires_operator_role(client: TestClient) -> None:
    response = client.post("/demo/flow", headers={"x-role": "shipper"})

    assert response.status_code == 403


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

    tasks = client.get("/tasks").json()
    task = next(item for item in tasks if item["entity_id"] == body["request"]["id"])
    assert task["priority"] == "high"
    assert "weight_kg is required" in task["reason"]


def test_create_request_rejects_unknown_transport_mode(client: TestClient) -> None:
    response = client.post(
        "/requests",
        json={
            "customer": "Scania",
            "origin": "Sodertalje",
            "destination": "Berlin",
            "mode": "space",
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

    assert response.status_code == 422


def test_create_and_send_quote(client: TestClient) -> None:
    created = client.post(
        "/quotes",
        json={
            "request_id": "req-001",
            "customer_price": 12300,
            "currency": "SEK",
        },
    )

    assert created.status_code == 201
    quote_id = created.json()["id"]

    sent = client.post(f"/quotes/{quote_id}/send")

    assert sent.status_code == 200
    body = sent.json()
    assert body["quote"]["status"] == "sent"
    assert body["outbound_reply"]["quote_id"] == quote_id
    assert body["outbound_reply"]["status"] == "queued"

    outbound = client.get("/emails/outbound")
    assert outbound.status_code == 200
    assert outbound.json()[0]["quote_id"] == quote_id

    detail = client.get(f"/quotes/{quote_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["line_items"][0]["description"] == "Freight charge"
    assert detail_body["line_items"][0]["amount"] == 12300
    assert detail_body["acceptance_events"][0]["event_type"] == "quote_sent"


def test_process_outbound_queue_marks_replies_sent(client: TestClient) -> None:
    created = client.post(
        "/quotes",
        json={
            "request_id": "req-001",
            "customer_price": 12300,
            "currency": "SEK",
        },
    )
    quote_id = created.json()["id"]
    client.post(f"/quotes/{quote_id}/send")

    processed = client.post("/emails/outbound/process", json={"limit": 10})

    assert processed.status_code == 200
    assert processed.json()["sent"][0]["quote_id"] == quote_id
    assert processed.json()["sent"][0]["status"] == "sent"
    assert processed.json()["failed"] == []

    outbound = client.get("/emails/outbound").json()
    assert outbound[0]["status"] == "sent"
    assert outbound[0]["sent_at"] is not None


def test_send_quote_blocks_zero_price(client: TestClient) -> None:
    response = client.post("/quotes/quo-002/send")

    assert response.status_code == 422
    assert response.json()["detail"] == "Quote customer price must be greater than zero"
    assert client.get("/emails/outbound").json() == []


def test_accept_quote_books_shipment_with_carrier_intelligence(client: TestClient) -> None:
    response = client.post(
        "/quotes/quo-001/accept",
        json={
            "mode": "ltl",
            "total_weight_kg": 820,
            "requested_carrier_name": "Nordic",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_carrier_id"] == "car-001"
    assert body["shipment"]["status"] == "booked"


def test_quote_reply_accepts_and_books_shipment(client: TestClient) -> None:
    response = client.post(
        "/quotes/quo-001/reply",
        json={
            "body_text": "Accepted, please go ahead",
            "mode": "ltl",
            "total_weight_kg": 820,
            "requested_carrier_name": "Nordic",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "accepted"
    assert body["event"]["intent"] == "accepted"
    assert body["quote"]["status"] == "accepted"
    assert body["shipment"]["status"] == "booked"

    detail = client.get("/quotes/quo-001").json()
    event_types = {event["event_type"] for event in detail["acceptance_events"]}
    assert "reply_accepted" in event_types


def test_quote_reply_rejects_quote(client: TestClient) -> None:
    response = client.post(
        "/quotes/quo-001/reply",
        json={"body_text": "No thanks, we reject this quote"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "rejected"
    assert body["quote"]["status"] == "rejected"
    assert body["shipment"] is None


def test_quote_reply_revision_creates_revised_quote(client: TestClient) -> None:
    response = client.post(
        "/quotes/quo-001/reply",
        json={
            "body_text": "Please revise with a lower price",
            "revised_customer_price": 17000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "revise"
    assert body["quote"]["status"] == "revision_requested"
    assert body["revised_quote"]["status"] == "revised"
    assert body["revised_quote"]["version"] == 2
    assert body["revised_quote"]["parent_quote_id"] == "quo-001"
    assert body["revised_quote"]["customer_price"] == 17000


def test_update_shipment_status_uses_fsm(client: TestClient) -> None:
    response = client.post("/shipments/shp-001/status", json={"status": "in_transit"})

    assert response.status_code == 200
    assert response.json()["status"] == "in_transit"

    timeline = client.get("/shipments/shp-001/timeline")
    assert timeline.status_code == 200
    assert timeline.json()[0]["from_status"] == "booked"
    assert timeline.json()[0]["to_status"] == "in_transit"


def test_update_shipment_status_rejects_invalid_transition(client: TestClient) -> None:
    response = client.post("/shipments/shp-001/status", json={"status": "invoice_approved"})

    assert response.status_code == 422


def test_manual_shipment_override_records_reason(client: TestClient) -> None:
    response = client.post(
        "/shipments/shp-001/override",
        json={
            "status": "needs_review",
            "reason": "Carrier confirmation requires operator review",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"

    timeline = client.get("/shipments/shp-001/timeline").json()
    assert timeline[0]["to_status"] == "needs_review"
    assert timeline[0]["reason"] == (
        "Manual override: Carrier confirmation requires operator review"
    )


def test_invoice_audit_approves_within_discrepancy(client: TestClient) -> None:
    client.post("/shipments/shp-001/status", json={"status": "in_transit"})
    client.post("/shipments/shp-001/status", json={"status": "delivered"})

    response = client.post(
        "/shipments/shp-001/invoice",
        json={"invoice_amount": 7350, "max_discrepancy": 250},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["invoice"]["status"] == "approved"
    assert body["shipment_status"] == "invoice_approved"


def test_invoice_audit_disputes_large_discrepancy(client: TestClient) -> None:
    client.post("/shipments/shp-001/status", json={"status": "in_transit"})
    client.post("/shipments/shp-001/status", json={"status": "delivered"})

    response = client.post(
        "/shipments/shp-001/invoice",
        json={"invoice_amount": 9000, "max_discrepancy": 250},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["invoice"]["status"] == "disputed"
    assert body["shipment_status"] == "invoice_disputed"


def test_tracking_simulator_delivers_and_auto_audits_invoice(client: TestClient) -> None:
    response = client.post(
        "/shipments/tracking-simulator/run",
        json={"limit": 10, "max_discrepancy": 250},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"][0]["id"] == "shp-002"
    assert body["delivered"][0]["status"] == "delivered"
    assert body["invoices"][0]["shipment_id"] == "shp-002"
    assert body["invoices"][0]["status"] == "approved"

    shipments = client.get("/shipments").json()
    shipment = next(item for item in shipments if item["id"] == "shp-002")
    assert shipment["status"] == "invoice_approved"

    timeline = client.get("/shipments/shp-002/timeline").json()
    transitions = [(event["from_status"], event["to_status"]) for event in timeline]
    assert ("in_transit", "delivered") in transitions
    assert ("delivered", "invoice_approved") in transitions


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


def test_agent_configs_can_be_listed_and_updated_by_admin(client: TestClient) -> None:
    listed = client.get("/agents/configs")

    assert listed.status_code == 200
    assert listed.json()[0]["agent_key"]

    updated = client.post(
        "/agents/intake_agent/config",
        json={
            "is_enabled": False,
            "auto_mode": "guarded_auto",
            "min_confidence": 0.91,
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["agent_key"] == "intake_agent"
    assert body["is_enabled"] is False
    assert body["auto_mode"] == "guarded_auto"
    assert body["min_confidence"] == 0.91

    configs = client.get("/agents/configs").json()
    intake = next(item for item in configs if item["agent_key"] == "intake_agent")
    assert intake["is_enabled"] is False
    assert intake["auto_mode"] == "guarded_auto"


def test_agent_config_update_requires_admin_role(client: TestClient) -> None:
    response = client.post(
        "/agents/intake_agent/config",
        headers={"x-role": "4pl_tower"},
        json={
            "is_enabled": True,
            "auto_mode": "manual",
            "min_confidence": 0.7,
        },
    )

    assert response.status_code == 403


def test_stale_request_escalator_creates_idempotent_tasks(client: TestClient) -> None:
    with client.app.state.container.database.connect() as connection:
        connection.execute(
            """
            update transport_requests
            set created_at = datetime('now', '-25 hours')
            where id = ?
            """,
            ("req-003",),
        )

    first_result = anyio.run(
        lambda: client.app.state.container.stale_request_escalator.run(
            EscalateStaleRequestsCommand(max_age_hours=24)
        )
    )
    second_result = anyio.run(
        lambda: client.app.state.container.stale_request_escalator.run(
            EscalateStaleRequestsCommand(max_age_hours=24)
        )
    )

    assert len(first_result.tasks) == 1
    assert len(second_result.tasks) == 0

    tasks = client.get("/tasks").json()
    stale_tasks = [
        task
        for task in tasks
        if task["entity_id"] == "req-003"
        and task["reason"].startswith("Stale clarification request")
    ]
    assert len(stale_tasks) == 1
    assert stale_tasks[0]["priority"] == "high"
