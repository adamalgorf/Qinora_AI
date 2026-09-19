"""A sender who confirms an order but isn't a known customer is asked for
their company details, and their reply registers them as a customer
(application/customer_onboarding.py, driven by the email intake orchestrator).
"""

from dataclasses import dataclass, field, replace

import anyio
import pytest
from test_email_intake_orchestrator import (
    FakeAgentConfigRepository,
    FakeAgentLogWriteRepository,
    FakeClarificationOutboundRepository,
    FakeOperationalTaskWriteRepository,
    _build_orchestrator,
    _email,
    _parsek_config,
)

from qinora.application.agent_config import AgentConfigService
from qinora.application.customer_import import CustomerImportService, CustomerInput
from qinora.application.customer_onboarding import (
    REQUIRED_DETAILS,
    CustomerOnboardingService,
    replies_since_acceptance,
)
from qinora.application.read_models import (
    ContactRecord,
    InboundEmailRecord,
    ParsedCustomerDetails,
    QuoteDetailRecord,
    QuoteRecord,
    RequestDetailRecord,
    RequestRecord,
)
from qinora.application.thread_matching import ThreadMatchResult

SENDER = "anna@ekeby.example"


@dataclass
class FakeCustomerDetailsLLM:
    result: ParsedCustomerDetails
    raw_texts: list = field(default_factory=list)

    async def parse(self, *, raw_text: str) -> ParsedCustomerDetails:
        self.raw_texts.append(raw_text)
        return self.result


@dataclass
class FakeContactWriteRepository:
    created: list = field(default_factory=list)

    async def create_contact(self, customer: CustomerInput) -> ContactRecord:
        number = len(self.created) + 1
        record = ContactRecord(
            id=f"cnt-new-{number}",
            public_id=f"CNT-90{number:02d}",
            display_name=customer.display_name,
            email=customer.email,
            domain=customer.domain,
            default_markup_percent=customer.default_markup_percent,
            default_incoterms=None,
            payment_terms=None,
            org_number=customer.org_number,
            contact_person=customer.contact_person,
            contact_email=customer.contact_email,
            contact_phone=customer.contact_phone,
            address=customer.address,
        )
        self.created.append(record)
        return record


class FailingClarificationOutbound(FakeClarificationOutboundRepository):
    async def enqueue(self, **kwargs):
        raise RuntimeError("mail queue down")


def _details(**overrides) -> ParsedCustomerDetails:
    values = {
        "provides_details": True,
        "company_name": "Ekeby Transport AB",
        "org_number": "556677-8899",
        "address": "Storgatan 1, 111 22 Stockholm",
        "contact_person": "Anna Andersson",
        "contact_email": "anna@ekeby.example",
        "contact_phone": "070-123 45 67",
        "confidence": 0.95,
    }
    values.update(overrides)
    return ParsedCustomerDetails(**values)


class _Harness:
    def __init__(
        self,
        *,
        email: InboundEmailRecord,
        quote_status: str,
        details: ParsedCustomerDetails | None = None,
        existing_customers: list[ContactRecord] | None = None,
        known_contact: ContactRecord | None = None,
        history: list[InboundEmailRecord] | None = None,
        outbound: FakeClarificationOutboundRepository | None = None,
        nora_confidence: float = 0.74,
    ) -> None:
        self.email = email
        self.outbound = outbound or FakeClarificationOutboundRepository()
        self.tasks = FakeOperationalTaskWriteRepository()
        self.agent_logs = FakeAgentLogWriteRepository()
        self.llm = FakeCustomerDetailsLLM(details or _details())
        self.writes = FakeContactWriteRepository()

        async def existing() -> list[ContactRecord]:
            return list(existing_customers or [])

        config = replace(_parsek_config(), min_confidence=nora_confidence)
        onboarding = CustomerOnboardingService(
            parsing_llm=self.llm,
            customers=CustomerImportService(self.writes, existing),
            clarification_outbound=self.outbound,
            task_repository=self.tasks,
            agent_logs=self.agent_logs,
            agent_config=AgentConfigService(FakeAgentConfigRepository(configs=[config])),
        )

        quote = QuoteRecord(
            id="quo-1",
            status=quote_status,
            version=1,
            customer_price=1000,
            currency="SEK",
            parent_quote_id=None,
            request_id="req-1",
        )
        (
            self.orchestrator,
            self.email_threads,
            _contacts,
            _tasks,
            self.shipments,
            self.quotes,
            self.request_llm,
            self.requests,
            *_,
        ) = _build_orchestrator(
            email=email,
            parsek_config=config,
            thread_match=ThreadMatchResult(
                request_id="req-1", quote_id="quo-1", matched_email_id="mail-old", tier=1
            ),
            quote_details={
                "quo-1": QuoteDetailRecord(quote=quote, line_items=(), acceptance_events=())
            },
            request_details={
                "req-1": RequestDetailRecord(
                    request=RequestRecord(
                        id="req-1",
                        public_id="REQ-0001",
                        customer="Ekeby Transport AB",
                        lane="Gothenburg -> Hamburg",
                        mode="ltl",
                        status="quoted",
                        weight_kg=820,
                    ),
                    review_reason=None,
                    created_at="2026-01-01T00:00:00",
                    cargo_lines=(),
                )
            },
            seed_quotes={"quo-1": quote},
            contact=known_contact,
            clarification_outbound=self.outbound,
            customer_onboarding=onboarding,
            task_repository=self.tasks,
            email_history=history,
        )

    def handle(self):
        return anyio.run(lambda: self.orchestrator.handle(self.email.id))


def _accept_email(**kwargs) -> InboundEmailRecord:
    return _email("mail-accept", sender=SENDER, body_text="We accept, please proceed", **kwargs)


def _reply_email(body_text: str = "Här är våra uppgifter ...") -> InboundEmailRecord:
    return replace(
        _email("mail-reply", sender=SENDER, body_text=body_text, subject="Re: Din offert - quo-1"),
        sender_name="Anna Andersson",
    )


def _accepted_history() -> list[InboundEmailRecord]:
    original = replace(
        _email(
            "mail-original",
            sender=SENDER,
            body_text="Hämtas på Hamngatan 5, Göteborg - levereras i Hamburg",
        ),
        classification="transport_request",
    )
    confirmation = replace(
        _email("mail-accept", sender=SENDER, body_text="We accept, please proceed"),
        classification="accepted",
    )
    return [original, confirmation]


# --- asking for the details -------------------------------------------------


def test_unknown_sender_confirming_an_order_is_booked_and_asked_for_company_details() -> None:
    harness = _Harness(email=_accept_email(), quote_status="sent")

    result = harness.handle()

    assert result.classification == "accepted"
    assert len(harness.shipments.created) == 1  # booking is never held up
    [ask] = harness.outbound.enqueued
    assert ask["recipient"] == SENDER
    assert ask["inbound_email_id"] == "mail-accept"
    for _, label in REQUIRED_DETAILS:
        assert label in ask["body_text"]
    assert "org" in ask["body_text"].lower()
    assert any("bad om företagsuppgifter" in log.step for log in harness.agent_logs.logs)
    assert harness.tasks.created == []


def test_known_customer_confirming_an_order_is_not_asked_for_anything() -> None:
    known = ContactRecord(
        id="cnt-001",
        public_id="CNT-0001",
        display_name="Volvo Parts",
        email=SENDER,
        domain="ekeby.example",
        default_markup_percent=12.5,
        default_incoterms=None,
        payment_terms=None,
    )
    harness = _Harness(email=_accept_email(), quote_status="sent", known_contact=known)

    result = harness.handle()

    assert result.classification == "accepted"
    assert len(harness.shipments.created) == 1
    assert harness.outbound.enqueued == []


def test_failure_to_send_the_details_request_never_undoes_the_booking() -> None:
    harness = _Harness(
        email=_accept_email(), quote_status="sent", outbound=FailingClarificationOutbound()
    )

    result = harness.handle()

    assert result.classification == "accepted"  # not "error"
    assert len(harness.shipments.created) == 1
    [task] = harness.tasks.created
    assert "företagsuppgifter" in task["reason"]


# --- registering the customer from the reply --------------------------------


def test_complete_reply_registers_the_new_customer_and_thanks_them() -> None:
    harness = _Harness(
        email=_reply_email(), quote_status="accepted", history=_accepted_history()
    )

    result = harness.handle()

    assert result.classification == "customer_details"
    [customer] = harness.writes.created
    assert customer.display_name == "Ekeby Transport AB"
    assert customer.org_number == "556677-8899"
    assert customer.address == "Storgatan 1, 111 22 Stockholm"
    assert customer.contact_person == "Anna Andersson"
    assert customer.contact_email == "anna@ekeby.example"
    assert customer.contact_phone == "070-123 45 67"
    # Registered under the sender's own address, so their next mail matches.
    assert customer.email == SENDER
    assert customer.domain == "ekeby.example"
    [thanks] = harness.outbound.enqueued
    assert "Ekeby Transport AB" in thanks["body_text"]
    assert "556677-8899" in thanks["body_text"]
    assert harness.tasks.created == []
    # Handled as onboarding - not mistaken for a fresh transport request.
    assert harness.request_llm.calls == 0
    assert any("Registrerade ny kund" in log.step for log in harness.agent_logs.logs)


def test_partial_reply_gets_a_follow_up_for_only_what_is_missing() -> None:
    harness = _Harness(
        email=_reply_email(),
        quote_status="accepted",
        history=_accepted_history(),
        details=_details(contact_phone=None, address=None),
    )

    result = harness.handle()

    assert result.classification == "customer_details"
    assert harness.writes.created == []
    [follow_up] = harness.outbound.enqueued
    assert "telefonnummer" in follow_up["body_text"]
    assert "adress" in follow_up["body_text"]
    assert "Organisationsnummer" not in follow_up["body_text"]
    assert "Företagsnamn" not in follow_up["body_text"]


def test_reply_without_company_details_is_handled_like_any_other_reply() -> None:
    harness = _Harness(
        email=_reply_email("Tack, ses!"),
        quote_status="accepted",
        history=_accepted_history(),
        details=_details(provides_details=False),
    )

    result = harness.handle()

    assert result.classification != "customer_details"
    assert harness.writes.created == []
    assert harness.outbound.enqueued == []


def test_low_confidence_reply_is_escalated_instead_of_registering_a_customer() -> None:
    harness = _Harness(
        email=_reply_email(),
        quote_status="accepted",
        history=_accepted_history(),
        details=_details(confidence=0.4),
    )

    result = harness.handle()

    assert result.classification == "customer_details"
    assert harness.writes.created == []
    [task] = harness.tasks.created
    assert "granska kunduppgifter" in task["reason"]


def test_company_already_registered_under_that_name_is_escalated_not_duplicated() -> None:
    existing = ContactRecord(
        id="cnt-777",
        public_id="CNT-0777",
        display_name="ekeby transport ab",
        email="other@ekeby.example",
        domain=None,
        default_markup_percent=0,
        default_incoterms=None,
        payment_terms=None,
    )
    harness = _Harness(
        email=_reply_email(),
        quote_status="accepted",
        history=_accepted_history(),
        existing_customers=[existing],
    )

    result = harness.handle()

    assert result.classification == "customer_details"
    assert harness.writes.created == []
    [thanks] = harness.outbound.enqueued  # they still get their acknowledgment
    assert "Tack" in thanks["body_text"]
    [task] = harness.tasks.created
    assert "finns redan" in task["reason"]


def test_reply_from_an_already_known_customer_is_never_read_as_onboarding() -> None:
    known = ContactRecord(
        id="cnt-001",
        public_id="CNT-0001",
        display_name="Volvo Parts",
        email=SENDER,
        domain=None,
        default_markup_percent=0,
        default_incoterms=None,
        payment_terms=None,
    )
    harness = _Harness(
        email=_reply_email(),
        quote_status="accepted",
        history=_accepted_history(),
        known_contact=known,
    )

    harness.handle()

    assert harness.llm.raw_texts == []
    assert harness.writes.created == []


def test_only_messages_after_the_confirmation_are_read_for_company_details() -> None:
    later_message = replace(
        _email("mail-later", sender=SENDER, body_text="Org.nr 556677-8899"),
        classification="pending",
    )
    from_someone_else = replace(
        _email("mail-carrier", sender="dispatch@nordic.example", body_text="Pris 8500"),
        classification="carrier_offer",
    )
    history = [*_accepted_history(), from_someone_else, later_message]
    harness = _Harness(email=_reply_email("Adress: Storgatan 1"), quote_status="accepted",
                       history=history)

    harness.handle()

    [text] = harness.llm.raw_texts
    assert "Org.nr 556677-8899" in text
    assert "Adress: Storgatan 1" in text
    # The original request (pickup address) and the carrier's mail stay out.
    assert "Hamngatan" not in text
    assert "Pris 8500" not in text


@pytest.mark.parametrize("history", [[], [_email("mail-x", body_text="hej")]])
def test_no_recorded_confirmation_means_no_earlier_messages_are_read(history) -> None:
    assert replies_since_acceptance(history, _reply_email()) == []


# --- against the real SQLite stack ------------------------------------------


def test_registered_customer_shows_up_in_the_register_and_matches_the_next_mail(
    monkeypatch, tmp_path
) -> None:
    from fastapi.testclient import TestClient

    from qinora.infrastructure.sqlite import SQLiteContactReadRepository
    from qinora.interfaces.http.app import create_app

    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "false")
    client = TestClient(create_app())
    container = client.app.state.container
    onboarding = container.email_intake_orchestrator._customer_onboarding
    assert onboarding is not None  # wired into the real container
    onboarding._parsing_llm = FakeCustomerDetailsLLM(_details())

    async def run():
        outcome = await onboarding.handle_reply(_reply_email(), _accepted_history())
        matched = await SQLiteContactReadRepository(container.database).find_by_sender(
            "kollega@ekeby.example"
        )
        queued = await container.clarification_outbound_repository.next_queued(10)
        return outcome, matched, queued

    outcome, matched, queued = anyio.run(run)

    assert outcome is not None and outcome.status == "created"
    [customer] = [
        item
        for item in client.get("/contacts").json()
        if item["display_name"] == "Ekeby Transport AB"
    ]
    assert customer["org_number"] == "556677-8899"
    assert customer["address"] == "Storgatan 1, 111 22 Stockholm"
    assert customer["contact_person"] == "Anna Andersson"
    assert customer["contact_email"] == "anna@ekeby.example"
    assert customer["contact_phone"] == "070-123 45 67"
    assert client.get(f"/contacts/{customer['id']}").json()["org_number"] == "556677-8899"
    # A colleague at the same company is now recognised as this customer.
    assert matched is not None and matched.display_name == "Ekeby Transport AB"
    assert [item.recipient for item in queued] == [SENDER]


def test_customer_form_and_csv_import_accept_the_company_details(monkeypatch, tmp_path) -> None:
    from fastapi.testclient import TestClient

    from qinora.interfaces.http.app import create_app

    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "false")
    client = TestClient(create_app())

    created = client.post(
        "/contacts",
        json={
            "display_name": "Formulär AB",
            "org_number": "5566778899",
            "contact_person": "Nils",
            "contact_email": "Nils@Formular.example",
            "contact_phone": "08-123 456",
            "address": "Vägen 2, 123 45 Ort",
        },
    ).json()
    assert created["org_number"] == "556677-8899"  # normalised
    assert created["contact_email"] == "nils@formular.example"

    csv_content = "Kundnamn;Orgnr;Adress;Telefon\nCsv AB;5511223344;Gatan 1;070-111 22 33\n"
    imported = client.post(
        "/contacts/import", files={"file": ("k.csv", csv_content.encode(), "text/csv")}
    ).json()
    assert imported["created"][0]["org_number"] == "551122-3344"
    assert imported["created"][0]["contact_phone"] == "070-111 22 33"


def test_full_flow_through_the_email_webhook(monkeypatch, tmp_path) -> None:
    """Order confirmed by an unknown sender -> details requested -> the reply
    registers the customer. Real webhook, orchestrator, thread matching and
    SQLite; only the LLM reading the reply is faked.
    """
    import hmac
    import json
    from hashlib import sha256

    from fastapi.testclient import TestClient

    from qinora.interfaces.http.app import create_app

    monkeypatch.setenv("EMAIL_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("QINORA_SQLITE_PATH", str(tmp_path / "qinora_test.sqlite3"))
    monkeypatch.setenv("QINORA_REQUIRE_AUTH", "false")
    client = TestClient(create_app())
    container = client.app.state.container
    container.email_intake_orchestrator._customer_onboarding._parsing_llm = (
        FakeCustomerDetailsLLM(_details())
    )

    def post_email(key: str, *, subject: str, body_text: str) -> str:
        payload = json.dumps(
            {
                "sender": SENDER,
                "sender_name": "Anna Andersson",
                "recipient": "farah@qinora.org",
                "subject": subject,
                "body_text": body_text,
            }
        ).encode()
        signature = hmac.new(b"secret", payload, sha256).hexdigest()
        response = client.post(
            "/webhooks/email",
            headers={
                "content-type": "application/json",
                "x-idempotency-key": key,
                "x-qinora-signature": f"sha256={signature}",
            },
            content=payload,
        )
        assert response.status_code == 202
        return response.json()["inbound_email_id"]

    def classification_of(email_id: str) -> str:
        return client.get(f"/inbox/{email_id}").json()["message"]["classification"]

    def onboarding_asks() -> int:
        queued = anyio.run(lambda: container.clarification_outbound_repository.next_queued(50))
        return len([item for item in queued if "Organisationsnummer" in item.body_text])

    # A real quote (uuid id, like production) that has been sent to the customer.
    quote = client.post(
        "/quotes", json={"request_id": "req-001", "customer_price": 18400}
    ).json()
    assert client.post(f"/quotes/{quote['id']}/send").status_code == 200
    requests_before = len(client.get("/requests").json())
    subject = f"Re: Din offert - {quote['id']}"
    assert SENDER not in [c["email"] for c in client.get("/contacts").json()]

    # 1. Unknown sender confirms the order.
    accept_id = post_email("mail-1", subject=subject, body_text="We accept, please proceed")

    assert classification_of(accept_id) == "accepted"
    queued = anyio.run(lambda: container.clarification_outbound_repository.next_queued(10))
    [ask] = [item for item in queued if item.recipient == SENDER]
    assert "Organisationsnummer" in ask.body_text
    assert "Kontaktpersonens telefonnummer" in ask.body_text
    # ...and no customer exists yet, only the request for the details.
    assert "Ekeby Transport AB" not in [c["display_name"] for c in client.get("/contacts").json()]

    # 2. They answer with their company details.
    reply_id = post_email(
        "mail-2", subject=subject, body_text="Ekeby Transport AB, 556677-8899, ..."
    )

    assert classification_of(reply_id) == "customer_details"
    customers = {c["display_name"]: c for c in client.get("/contacts").json()}
    assert customers["Ekeby Transport AB"]["org_number"] == "556677-8899"
    assert customers["Ekeby Transport AB"]["email"] == SENDER
    # The answer was not mistaken for a new transport request.
    assert len(client.get("/requests").json()) == requests_before

    # 3. From now on the sender is a known customer: their next mail is
    # handled like any other customer's, and nothing more is asked of them.
    thanks_id = post_email("mail-3", subject=subject, body_text="Tack!")
    assert classification_of(thanks_id) != "customer_details"
    assert onboarding_asks() == 1
