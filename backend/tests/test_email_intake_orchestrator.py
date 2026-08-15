from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import anyio

from qinora.application.agent_config import AgentConfigService
from qinora.application.booking_workflow import BookingWorkflow
from qinora.application.contact_matching import ContactMatchingUseCase
from qinora.application.email_intake_orchestrator import EmailIntakeOrchestrator
from qinora.application.operational_queries import OperationalQueries
from qinora.application.pricing_engine import PricingEngine
from qinora.application.quote_workflow import QuoteWorkflow
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    ContactRecord,
    InboundEmailRecord,
    OutboundReplyRecord,
    ParsedCargoLine,
    ParsedTransportRequestDraft,
    QuoteDetailRecord,
    QuoteRecord,
    RateProfileRecord,
    RequestDetailRecord,
    RequestRecord,
    ShipmentRecord,
)
from qinora.application.request_intake import CreateRequestUseCase
from qinora.application.request_parsing_agent import RequestParsingAgent
from qinora.application.thread_matching import ThreadMatchResult
from qinora.domain import CurrencyCode, Money, Quote, QuoteStatus

# --- shared fakes -------------------------------------------------------


@dataclass
class FakeThreadMatcher:
    result: ThreadMatchResult | None = None

    async def match(self, **kwargs):
        return self.result


@dataclass
class FakeEmailThreadRepository:
    emails: dict
    linked: list = field(default_factory=list)
    classifications: dict = field(default_factory=dict)

    async def get(self, email_id):
        return self.emails.get(email_id)

    async def find_candidates_by_message_ids(self, message_ids):
        return []

    async def find_candidates_by_sender(self, sender, limit=200):
        return []

    async def find_candidates_by_domain(self, domain, limit=200):
        return []

    async def list_thread_history(self, *, request_id, quote_id):
        return []

    async def link_thread(self, email_id, *, request_id, quote_id):
        self.linked.append((email_id, request_id, quote_id))

    async def mark_classification(self, email_id, classification):
        self.classifications[email_id] = classification


@dataclass
class FakeContactReadRepository:
    contact: ContactRecord | None = None
    calls: int = 0

    async def find_by_sender(self, sender):
        self.calls += 1
        return self.contact


@dataclass
class FakeAgentLogWriteRepository:
    logs: list = field(default_factory=list)

    async def record(self, *, agent_key, agent_name, step, entity_id, confidence):
        log = AgentLogRecord(
            agent_key=agent_key,
            agent_name=agent_name,
            step=step,
            entity_id=entity_id,
            confidence=confidence,
        )
        self.logs.append(log)
        return log


@dataclass
class FakeAgentConfigRepository:
    configs: list

    async def list_configs(self):
        return self.configs

    async def update_config(self, **kwargs):
        raise NotImplementedError


@dataclass
class FakeOperationalTaskWriteRepository:
    created: list = field(default_factory=list)

    async def create_task(self, *, entity_type, entity_id, reason, priority="normal"):
        self.created.append(
            {"entity_type": entity_type, "entity_id": entity_id, "reason": reason}
        )
        return None


@dataclass
class FakeQuoteWriteRepository:
    quotes: dict = field(default_factory=dict)

    async def create_quote(self, *, request_id, customer_price, currency):
        quote_id = f"quo-{len(self.quotes) + 1}"
        record = QuoteRecord(
            id=quote_id,
            status="draft",
            version=1,
            customer_price=customer_price,
            currency=currency,
            parent_quote_id=None,
            request_id=request_id,
        )
        self.quotes[quote_id] = record
        return record

    async def get_quote(self, quote_id):
        record = self.quotes[quote_id]
        return Quote(
            id=record.id,
            status=QuoteStatus(record.status),
            version=record.version,
            customer_price=Money(
                amount=record.customer_price, currency=CurrencyCode(record.currency)
            ),
            parent_quote_id=record.parent_quote_id,
        )

    async def get_quote_record(self, quote_id):
        return self.quotes.get(quote_id)

    async def mark_quote_sent(self, quote_id):
        self.quotes[quote_id] = replace(self.quotes[quote_id], status="sent")
        return self.quotes[quote_id]

    async def mark_quote_accepted(self, quote_id):
        self.quotes[quote_id] = replace(self.quotes[quote_id], status="accepted")
        return self.quotes[quote_id]

    async def mark_quote_rejected(self, quote_id):
        raise NotImplementedError

    async def mark_quote_revision_requested(self, quote_id):
        raise NotImplementedError

    async def create_revision(self, **kwargs):
        raise NotImplementedError


@dataclass
class FakeOutboundReplyRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue_quote(self, *, quote_id, recipient, subject, body_text):
        record = OutboundReplyRecord(
            id="reply-1",
            quote_id=quote_id,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            status="queued",
            created_at="2026-01-01T00:00:00",
        )
        self.enqueued.append(record)
        return record

    async def next_queued(self, limit):
        raise NotImplementedError

    async def mark_sent(self, reply_id):
        raise NotImplementedError

    async def mark_failed(self, reply_id, error_message):
        raise NotImplementedError


@dataclass
class FakeShipmentWriteRepository:
    created: list = field(default_factory=list)

    async def get_shipment(self, shipment_id):
        return None

    async def create_shipment(self, *, quote_id, carrier_id, lane, status, eta):
        record = ShipmentRecord(
            id="shp-1",
            public_id="SHP-0001",
            quote_id=quote_id,
            carrier_id=carrier_id,
            lane=lane,
            status=status,
            eta=eta,
        )
        self.created.append(record)
        return record

    async def update_status(self, shipment_id, status):
        raise NotImplementedError


@dataclass
class FakeOperationalReadRepository:
    quote_details: dict = field(default_factory=dict)
    request_details: dict = field(default_factory=dict)
    shipments: list = field(default_factory=list)
    requests: list = field(default_factory=list)

    async def list_requests(self):
        return self.requests

    async def get_request_detail(self, request_id):
        return self.request_details.get(request_id)

    async def list_quotes(self):
        return []

    async def get_quote_detail(self, quote_id):
        return self.quote_details.get(quote_id)

    async def list_shipments(self):
        return self.shipments

    async def list_invoices(self):
        return []

    async def list_carriers(self):
        return []

    async def list_contacts(self):
        return []

    async def list_inbox(self):
        return []

    async def get_inbox_detail(self, message_id):
        return None

    async def list_agent_logs(self):
        return []

    async def list_operational_tasks(self):
        return []

    async def list_shipment_events(self, shipment_id):
        return []

    async def list_outbound_replies(self):
        return []


@dataclass
class FakeRequestParsingLLM:
    draft: ParsedTransportRequestDraft
    calls: int = 0

    async def parse(self, *, raw_text: str):
        self.calls += 1
        return self.draft


@dataclass
class FakeRequestWriteRepository:
    created: list = field(default_factory=list)

    async def create_transport_request(self, *, customer, lane, request, status, review_reason):
        record = RequestRecord(
            id="req-new",
            public_id="REQ-0100",
            customer=customer,
            lane=lane,
            mode=request.mode.value,
            status=status,
            weight_kg=sum(c.weight_kg or 0 for c in request.cargo),
        )
        self.created.append(record)
        return record

    async def update_transport_request(self, **kwargs):
        raise NotImplementedError


@dataclass
class FakeRateProfileRepository:
    profile: RateProfileRecord | None

    async def find_matching(self, *, mode, origin, destination):
        return self.profile

    async def list_all(self):
        return [self.profile] if self.profile else []

    async def create(self, **kwargs):
        raise NotImplementedError

    async def update(self, rate_profile_id, **kwargs):
        raise NotImplementedError


def _email(
    id: str,
    *,
    sender: str = "logistics@volvo.example",
    recipient: str = "farah@qinora.org",
    subject: str = "Quote request Hamburg",
    body_text: str = "Need pickup",
) -> InboundEmailRecord:
    return InboundEmailRecord(
        id=id,
        sender=sender,
        recipient=recipient,
        subject=subject,
        body_text=body_text,
        classification="pending",
        message_id=None,
        in_reply_to=None,
        references_header=None,
        request_id=None,
        quote_id=None,
        created_at=datetime.now(UTC).isoformat(),
    )


def _parsek_config(config: dict | None = None) -> AgentConfigRecord:
    return AgentConfigRecord(
        agent_key="request_parsing_agent",
        agent_name="Parsek",
        is_enabled=True,
        auto_mode="guarded_auto",
        min_confidence=0.74,
        config=config or {},
    )


def _build_orchestrator(
    *,
    email: InboundEmailRecord,
    parsek_config: AgentConfigRecord,
    thread_match: ThreadMatchResult | None = None,
    quote_details: dict | None = None,
    request_details: dict | None = None,
    shipments: list | None = None,
    llm_draft: ParsedTransportRequestDraft | None = None,
    rate_profile: RateProfileRecord | None = None,
    contact: ContactRecord | None = None,
    requests: list | None = None,
    seed_quotes: dict | None = None,
):
    email_threads = FakeEmailThreadRepository(emails={email.id: email})
    contacts = FakeContactReadRepository(contact=contact)
    contact_matching = ContactMatchingUseCase(contacts, FakeAgentLogWriteRepository())
    agent_config = AgentConfigService(FakeAgentConfigRepository(configs=[parsek_config]))

    operational_repo = FakeOperationalReadRepository(
        quote_details=quote_details or {},
        request_details=request_details or {},
        shipments=shipments or [],
        requests=requests or [],
    )
    operational_queries = OperationalQueries(operational_repo)

    quote_repository = FakeQuoteWriteRepository(quotes=dict(seed_quotes or {}))
    outbound_repository = FakeOutboundReplyRepository()
    shipment_repository = FakeShipmentWriteRepository()
    booking_workflow = BookingWorkflow(quote_repository, shipment_repository, operational_queries)

    task_repository = FakeOperationalTaskWriteRepository()

    llm = FakeRequestParsingLLM(
        draft=llm_draft
        or ParsedTransportRequestDraft(
            mode="ftl",
            origin="",
            destination="",
            cargo=(),
            loading_time=None,
            unloading_time=None,
            confidence=0.0,
            missing_fields=("origin", "destination", "cargo"),
        )
    )
    request_repository = FakeRequestWriteRepository()
    create_request = CreateRequestUseCase(request_repository, task_repository)
    request_parsing_agent = RequestParsingAgent(
        llm,
        create_request,
        FakeAgentLogWriteRepository(),
        agent_config,
        task_repository=task_repository,
    )

    quote_workflow = QuoteWorkflow(quote_repository, outbound_repository, operational_queries)
    pricing_engine = PricingEngine(
        FakeRateProfileRepository(rate_profile),
        quote_workflow,
        task_repository,
        default_markup_percent=15,
    )

    orchestrator = EmailIntakeOrchestrator(
        agent_config,
        contact_matching,
        FakeThreadMatcher(thread_match),
        email_threads,
        operational_queries,
        booking_workflow,
        task_repository,
        request_parsing_agent,
        pricing_engine,
    )
    return (
        orchestrator,
        email_threads,
        contacts,
        task_repository,
        shipment_repository,
        quote_repository,
        llm,
        request_repository,
    )


def test_loop_guard_rejects_own_mail_without_touching_anything() -> None:
    email = _email("mail-1", sender="bot@qinora.org")
    parsek_config = _parsek_config({"own_addresses": ["bot@qinora.org"]})
    orchestrator, email_threads, contacts, task_repository, *_ = _build_orchestrator(
        email=email, parsek_config=parsek_config
    )

    result = anyio.run(lambda: orchestrator.handle("mail-1"))

    assert result.classification == "rejected"
    assert email_threads.classifications["mail-1"] == "rejected"
    assert contacts.calls == 0
    assert task_repository.created == []
    assert email_threads.linked == []


def test_acceptance_shortcut_books_shipment_without_calling_llm() -> None:
    email = _email("mail-2", body_text="We accept, please proceed")
    parsek_config = _parsek_config()
    thread_match = ThreadMatchResult(
        request_id="req-1", quote_id="quo-1", matched_email_id="mail-old", tier=1
    )
    quote_details = {
        "quo-1": QuoteDetailRecord(
            quote=QuoteRecord(
                id="quo-1",
                status="sent",
                version=1,
                customer_price=1000,
                currency="SEK",
                parent_quote_id=None,
                request_id="req-1",
            ),
            line_items=(),
            acceptance_events=(),
        )
    }
    request_details = {
        "req-1": RequestDetailRecord(
            request=RequestRecord(
                id="req-1",
                public_id="REQ-0001",
                customer="Volvo Parts",
                lane="Gothenburg -> Hamburg",
                mode="ltl",
                status="quoted",
                weight_kg=820,
            ),
            review_reason=None,
            created_at="2026-01-01T00:00:00",
            cargo_lines=(),
        )
    }

    (
        orchestrator,
        email_threads,
        _contacts,
        task_repository,
        shipment_repository,
        quote_repository,
        llm,
        _request_repository,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        thread_match=thread_match,
        quote_details=quote_details,
        request_details=request_details,
        seed_quotes={"quo-1": quote_details["quo-1"].quote},
    )

    result = anyio.run(lambda: orchestrator.handle("mail-2"))

    assert result.classification == "accepted"
    assert email_threads.classifications["mail-2"] == "accepted"
    assert ("mail-2", "req-1", "quo-1") in email_threads.linked
    assert quote_repository.quotes["quo-1"].status == "accepted"
    assert len(shipment_repository.created) == 1
    assert shipment_repository.created[0].quote_id == "quo-1"
    assert task_repository.created == []
    # The deterministic keyword classifier handled this - Parsek's LLM was
    # never invoked for the accept path.
    assert llm.calls == 0


def test_closed_thread_escalates_instead_of_auto_processing() -> None:
    email = _email("mail-3", subject="Re: Old request", body_text="Any update?")
    parsek_config = _parsek_config()
    thread_match = ThreadMatchResult(
        request_id="req-2", quote_id=None, matched_email_id="mail-old2", tier=2
    )
    request_details = {
        "req-2": RequestDetailRecord(
            request=RequestRecord(
                id="req-2",
                public_id="REQ-0002",
                customer="Northvolt",
                lane="Skelleftea -> Rotterdam",
                mode="ftl",
                status="converted",
                weight_kg=15500,
            ),
            review_reason=None,
            created_at="2026-01-01T00:00:00",
            cargo_lines=(),
        )
    }

    (
        orchestrator,
        email_threads,
        _contacts,
        task_repository,
        _shipment_repository,
        _quote_repository,
        llm,
        request_repository,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        thread_match=thread_match,
        request_details=request_details,
    )

    result = anyio.run(lambda: orchestrator.handle("mail-3"))

    assert result.classification == "closed_thread"
    assert task_repository.created == [
        {
            "entity_type": "transport_request",
            "entity_id": "req-2",
            "reason": "granska och svara manuellt",
        }
    ]
    assert ("mail-3", "req-2", None) in email_threads.linked
    assert llm.calls == 0
    assert request_repository.created == []


def test_new_thread_creates_request_and_prices_it() -> None:
    email = _email(
        "mail-4",
        sender="ops@northvolt.example",
        subject="New FTL request",
        body_text="500kg pallets Gothenburg to Malmo, pickup 2026-06-01",
    )
    parsek_config = _parsek_config()
    draft = ParsedTransportRequestDraft(
        mode="ltl",
        origin="Gothenburg",
        destination="Malmo",
        cargo=(ParsedCargoLine("Pallets", 4, 500.0, 120, 100, 150),),
        loading_time=datetime(2026, 6, 1, 10, tzinfo=UTC),
        unloading_time=None,
        confidence=0.9,
        missing_fields=(),
        action="create",
    )
    rate_profile = RateProfileRecord(
        id="rate-1",
        mode="ltl",
        origin=None,
        destination=None,
        base_price=100,
        price_per_kg=2,
        currency="SEK",
    )
    # Matches what FakeRequestWriteRepository.create_transport_request returns
    # below, so QuoteWorkflow.create_quote can find the newly created request.
    created_request = RequestRecord(
        id="req-new",
        public_id="REQ-0100",
        customer="ops@northvolt.example",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="parsed",
        weight_kg=500,
    )

    (
        orchestrator,
        email_threads,
        _contacts,
        task_repository,
        _shipment_repository,
        quote_repository,
        llm,
        request_repository,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        thread_match=None,
        llm_draft=draft,
        rate_profile=rate_profile,
        requests=[created_request],
    )

    result = anyio.run(lambda: orchestrator.handle("mail-4"))

    assert result.classification == "transport_request"
    assert llm.calls == 1
    assert request_repository.created[0].id == "req-new"
    assert ("mail-4", "req-new", None) in email_threads.linked
    assert len(quote_repository.quotes) == 1
    quote = next(iter(quote_repository.quotes.values()))
    # carrier_cost = 100 + 2*500 = 1100; customer_price = 1100 * 1.15 = 1265.0
    assert quote.customer_price == 1265.0
    assert quote.status == "sent"
    assert task_repository.created == []
