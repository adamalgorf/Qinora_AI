from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import anyio

from qinora.application.agent_config import AgentConfigService
from qinora.application.booking_workflow import BookingWorkflow
from qinora.application.carrier_offer_agent import (
    AGENT_KEY as CARRIER_OFFER_AGENT_KEY,
)
from qinora.application.carrier_offer_agent import (
    CarrierOfferParsingAgent,
)
from qinora.application.contact_matching import ContactMatchingUseCase
from qinora.application.email_intake_orchestrator import EmailIntakeOrchestrator
from qinora.application.operational_queries import OperationalQueries
from qinora.application.pricing_engine import PricingEngine
from qinora.application.quote_workflow import QuoteWorkflow
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    CarrierOfferRecord,
    CarrierRfqRecord,
    ContactRecord,
    InboundEmailRecord,
    OutboundReplyRecord,
    ParsedCargoLine,
    ParsedCarrierOfferDraft,
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
    status_updates: list = field(default_factory=list)

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

    async def update_request_status(self, request_id, status):
        self.status_updates.append((request_id, status))


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


@dataclass
class FakeCarrierRfqTargeting:
    targets: list = field(default_factory=list)

    async def select_targets(self, command):
        return self.targets


@dataclass
class FakeCarrierRfqOutboundRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue(self, *, carrier_rfq_id, recipient, subject, body_text):
        self.enqueued.append(
            {
                "carrier_rfq_id": carrier_rfq_id,
                "recipient": recipient,
                "subject": subject,
                "body_text": body_text,
            }
        )
        return None

    async def next_queued(self, limit):
        raise NotImplementedError

    async def mark_sent(self, item_id):
        raise NotImplementedError

    async def mark_failed(self, item_id, error_message):
        raise NotImplementedError


@dataclass
class FakeCarrierRfqRepository:
    """Backs both PricingEngine's carrier sourcing branch and the
    orchestrator's own carrier-reply matching - the same instance is wired
    to both in _build_orchestrator, mirroring how they share one real
    CarrierRfqRepository in interfaces/http/container.py.
    """

    by_token: dict = field(default_factory=dict)
    by_email: dict = field(default_factory=dict)
    open_batch: dict = field(default_factory=dict)
    responded: list = field(default_factory=list)
    created_batches: list = field(default_factory=list)

    async def create_batch(self, *, request_id, carrier_ids, window_hours=24):
        records = [
            CarrierRfqRecord(
                id=f"rfq-{request_id}-{carrier_id}",
                request_id=request_id,
                carrier_id=carrier_id,
                correlation_token=f"tok-{carrier_id}",
                status="sent",
                sent_at="2026-01-01T00:00:00",
                responded_at=None,
                expires_at="2026-01-02T00:00:00",
            )
            for carrier_id in carrier_ids
        ]
        self.created_batches.append({"request_id": request_id, "carrier_ids": carrier_ids})
        return records

    async def find_by_token(self, token):
        return self.by_token.get(token)

    async def find_by_carrier_email(self, sender_address):
        return self.by_email.get(sender_address.strip().lower())

    async def mark_responded(self, rfq_id, offer_id):
        self.responded.append((rfq_id, offer_id))
        return None

    async def list_open_batch(self, request_id):
        return self.open_batch.get(request_id, [])

    async def list_batch(self, request_id):
        raise NotImplementedError

    async def expire_stale(self, cutoff):
        raise NotImplementedError

    async def mark_superseded(self, rfq_ids):
        raise NotImplementedError

    async def find_winning(self, request_id):
        return None


@dataclass
class FakeCarrierOfferParsingLLM:
    draft: ParsedCarrierOfferDraft

    async def parse(self, *, raw_text: str):
        return self.draft


@dataclass
class FakeCarrierOfferWriteRepository:
    created: list = field(default_factory=list)

    async def create_offer(
        self,
        *,
        request_id,
        carrier_name,
        price,
        currency,
        transit_days,
        notes,
        confidence,
        carrier_rfq_id=None,
    ):
        record = CarrierOfferRecord(
            id=f"carrier-offer-{len(self.created) + 1}",
            request_id=request_id,
            carrier_name=carrier_name,
            price=price,
            currency=currency,
            transit_days=transit_days,
            notes=notes,
            confidence=confidence,
            created_at="2026-01-01T00:00:00",
            carrier_rfq_id=carrier_rfq_id,
        )
        self.created.append(record)
        return record

    async def list_offers_for_request(self, request_id):
        return [item for item in self.created if item.request_id == request_id]


@dataclass
class FakeCarrierRfqCollector:
    finalized: list = field(default_factory=list)

    async def finalize_batch(self, request_id):
        self.finalized.append(request_id)
        return None


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


def _carrier_offer_config(config: dict | None = None) -> AgentConfigRecord:
    return AgentConfigRecord(
        agent_key=CARRIER_OFFER_AGENT_KEY,
        agent_name="Remy Rates",
        is_enabled=True,
        auto_mode="guarded_auto",
        min_confidence=0.7,
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
    carrier_rfq_repository: FakeCarrierRfqRepository | None = None,
    carrier_offer_draft: ParsedCarrierOfferDraft | None = None,
    carrier_offer_agent_config: AgentConfigRecord | None = None,
):
    email_threads = FakeEmailThreadRepository(emails={email.id: email})
    contacts = FakeContactReadRepository(contact=contact)
    contact_matching = ContactMatchingUseCase(contacts, FakeAgentLogWriteRepository())
    agent_config = AgentConfigService(
        FakeAgentConfigRepository(
            configs=[parsek_config, carrier_offer_agent_config or _carrier_offer_config()]
        )
    )

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
    carrier_rfqs = carrier_rfq_repository or FakeCarrierRfqRepository()
    booking_workflow = BookingWorkflow(
        quote_repository,
        shipment_repository,
        operational_queries,
        carrier_rfqs,
        outbound_repository,
    )

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
        carrier_rfq_targeting=FakeCarrierRfqTargeting(),
        carrier_rfqs=carrier_rfqs,
        carrier_rfq_outbound=FakeCarrierRfqOutboundRepository(),
        request_repository=request_repository,
    )

    carrier_offer_repository = FakeCarrierOfferWriteRepository()
    carrier_offer_agent = CarrierOfferParsingAgent(
        FakeCarrierOfferParsingLLM(
            draft=carrier_offer_draft
            or ParsedCarrierOfferDraft(
                carrier_name="Nordic Freight",
                price=8500.0,
                currency="SEK",
                transit_days=2,
                notes=None,
                confidence=0.9,
                missing_fields=(),
            )
        ),
        carrier_offer_repository,
        FakeAgentLogWriteRepository(),
        agent_config,
    )
    carrier_rfq_collector = FakeCarrierRfqCollector()

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
        carrier_rfqs,
        carrier_offer_agent,
        carrier_rfq_collector,
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
        carrier_rfqs,
        carrier_offer_repository,
        carrier_rfq_collector,
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
        *_,
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
        *_,
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
        *_,
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


def test_carrier_reply_matched_by_token_routes_to_remy_rates_not_parsek() -> None:
    email = _email(
        "mail-5",
        sender="rates@nordic.example",
        subject="Re: QiNora RFQ #A1B2C3D4 - Gothenburg -> Malmo, ltl",
        body_text="We can do 8500 SEK, 2 days transit.",
    )
    parsek_config = _parsek_config()
    open_rfq = CarrierRfqRecord(
        id="rfq-1",
        request_id="req-1",
        carrier_id="car-1",
        correlation_token="A1B2C3D4",
        status="sent",
        sent_at="2026-01-01T00:00:00",
        responded_at=None,
        expires_at="2026-01-02T00:00:00",
    )
    carrier_rfqs = FakeCarrierRfqRepository(
        by_token={"A1B2C3D4": open_rfq},
        # Still one other open RFQ in the batch, so this reply alone
        # shouldn't finalize it yet.
        open_batch={"req-1": [open_rfq]},
    )

    (
        orchestrator,
        email_threads,
        _contacts,
        task_repository,
        *_,
        carrier_rfq_repository,
        carrier_offer_repository,
        carrier_rfq_collector,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        carrier_rfq_repository=carrier_rfqs,
    )

    result = anyio.run(lambda: orchestrator.handle("mail-5"))

    assert result.classification == "carrier_offer"
    assert email_threads.classifications["mail-5"] == "carrier_offer"
    assert ("mail-5", "req-1", None) in email_threads.linked
    # Remy Rates (carrier_offer_agent) parsed and saved the offer...
    assert len(carrier_offer_repository.created) == 1
    assert carrier_offer_repository.created[0].request_id == "req-1"
    # ...and the RFQ got linked to it via mark_responded, not Parsek.
    assert carrier_rfq_repository.responded == [
        ("rfq-1", carrier_offer_repository.created[0].id)
    ]
    assert task_repository.created == []
    # The batch still has another open RFQ (per open_batch above), so this
    # reply alone doesn't trigger Phase E finalization yet.
    assert carrier_rfq_collector.finalized == []


def test_carrier_reply_completing_batch_triggers_immediate_finalization() -> None:
    email = _email(
        "mail-6",
        sender="rates@nordic.example",
        subject="Re: QiNora RFQ #DEADBEEF - Gothenburg -> Malmo, ltl",
        body_text="We can do 8500 SEK, 2 days transit.",
    )
    parsek_config = _parsek_config()
    open_rfq = CarrierRfqRecord(
        id="rfq-2",
        request_id="req-2",
        carrier_id="car-1",
        correlation_token="DEADBEEF",
        status="sent",
        sent_at="2026-01-01T00:00:00",
        responded_at=None,
        expires_at="2026-01-02T00:00:00",
    )
    # No other open RFQs left once this one responds - list_open_batch
    # returns empty, which should trigger the collector's finalize_batch.
    carrier_rfqs = FakeCarrierRfqRepository(
        by_token={"DEADBEEF": open_rfq},
        open_batch={"req-2": []},
    )

    (
        orchestrator,
        *_,
        carrier_rfq_collector,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        carrier_rfq_repository=carrier_rfqs,
    )

    result = anyio.run(lambda: orchestrator.handle("mail-6"))

    assert result.classification == "carrier_offer"
    assert carrier_rfq_collector.finalized == ["req-2"]


def test_carrier_reply_matched_by_sender_email_fallback() -> None:
    email = _email(
        "mail-7",
        sender="rates@nordic.example",
        subject="Nordic Freight rate quote",  # no correlation token in subject
        body_text="8500 SEK, 2 days.",
    )
    parsek_config = _parsek_config()
    open_rfq = CarrierRfqRecord(
        id="rfq-3",
        request_id="req-3",
        carrier_id="car-1",
        correlation_token="FEEDFACE",
        status="sent",
        sent_at="2026-01-01T00:00:00",
        responded_at=None,
        expires_at="2026-01-02T00:00:00",
    )
    carrier_rfqs = FakeCarrierRfqRepository(
        by_email={"rates@nordic.example": open_rfq},
        open_batch={"req-3": [open_rfq]},
    )

    (
        orchestrator,
        email_threads,
        *_,
        carrier_rfq_repository,
        carrier_offer_repository,
        _carrier_rfq_collector,
    ) = _build_orchestrator(
        email=email,
        parsek_config=parsek_config,
        carrier_rfq_repository=carrier_rfqs,
    )

    result = anyio.run(lambda: orchestrator.handle("mail-7"))

    assert result.classification == "carrier_offer"
    assert ("mail-7", "req-3", None) in email_threads.linked
    assert carrier_rfq_repository.responded == [
        ("rfq-3", carrier_offer_repository.created[0].id)
    ]
