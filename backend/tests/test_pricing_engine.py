from dataclasses import dataclass, field, replace

import anyio

from qinora.application.operational_queries import OperationalQueries
from qinora.application.pricing_engine import (
    NO_CARRIERS_REASON,
    PriceAndQuoteCommand,
    PricingEngine,
)
from qinora.application.quote_workflow import QuoteWorkflow
from qinora.application.read_models import (
    CarrierRecord,
    CarrierRfqOutboundRecord,
    CarrierRfqRecord,
    ContactRecord,
    OutboundReplyRecord,
    RateProfileRecord,
    RequestRecord,
)
from qinora.domain import CurrencyCode, Money, Quote, QuoteStatus


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
class FakeQuoteWriteRepository:
    quotes: dict = field(default_factory=dict)

    async def create_quote(self, *, request_id, customer_price, currency):
        from qinora.application.read_models import QuoteRecord

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
        raise NotImplementedError

    async def mark_quote_rejected(self, quote_id):
        raise NotImplementedError

    async def mark_quote_revision_requested(self, quote_id):
        raise NotImplementedError

    async def create_revision(self, **kwargs):
        raise NotImplementedError


@dataclass
class FakeOutboundReplyRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue_quote(
        self, *, quote_id, recipient, subject, body_text, in_reply_to_message_id=None
    ):
        record = OutboundReplyRecord(
            id="reply-1",
            quote_id=quote_id,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            status="queued",
            created_at="2026-01-01T00:00:00",
            in_reply_to_message_id=in_reply_to_message_id,
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
class FakeOperationalReadRepository:
    requests: list

    async def list_requests(self):
        return self.requests

    async def get_request_detail(self, request_id):
        return None

    async def list_quotes(self):
        return []

    async def get_quote_detail(self, quote_id):
        return None

    async def list_shipments(self):
        return []

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
class FakeOperationalTaskWriteRepository:
    created: list = field(default_factory=list)

    async def create_task(self, *, entity_type, entity_id, reason, priority="normal"):
        self.created.append(
            {"entity_type": entity_type, "entity_id": entity_id, "reason": reason}
        )
        return None


@dataclass
class FakeCarrierRfqTargeting:
    targets: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    async def select_targets(self, command):
        self.calls.append(command)
        return self.targets


@dataclass
class FakeCarrierRfqRepository:
    created_batches: list = field(default_factory=list)
    _next_id: int = 1

    async def create_batch(self, *, request_id, carrier_ids, window_hours=24):
        records = []
        for carrier_id in carrier_ids:
            records.append(
                CarrierRfqRecord(
                    id=f"rfq-{self._next_id}",
                    request_id=request_id,
                    carrier_id=carrier_id,
                    correlation_token=f"token{self._next_id}",
                    status="sent",
                    sent_at="2026-01-01T00:00:00",
                    responded_at=None,
                    expires_at="2026-01-02T00:00:00",
                )
            )
            self._next_id += 1
        self.created_batches.append({"request_id": request_id, "carrier_ids": carrier_ids})
        return records

    async def find_by_token(self, token):
        raise NotImplementedError

    async def find_by_carrier_email(self, sender_address):
        raise NotImplementedError

    async def mark_responded(self, rfq_id, offer_id):
        raise NotImplementedError

    async def list_open_batch(self, request_id):
        raise NotImplementedError

    async def list_batch(self, request_id):
        raise NotImplementedError

    async def expire_stale(self, cutoff):
        raise NotImplementedError

    async def mark_superseded(self, rfq_ids):
        raise NotImplementedError


@dataclass
class FakeCarrierRfqOutboundRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue(self, *, carrier_rfq_id, recipient, subject, body_text):
        record = CarrierRfqOutboundRecord(
            id=f"cro-{len(self.enqueued) + 1}",
            carrier_rfq_id=carrier_rfq_id,
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

    async def mark_sent(self, item_id):
        raise NotImplementedError

    async def mark_failed(self, item_id, error_message):
        raise NotImplementedError


@dataclass
class FakeRequestWriteRepository:
    status_updates: list = field(default_factory=list)

    async def create_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_request_status(self, request_id, status):
        self.status_updates.append((request_id, status))


def _quote_workflow(
    request: RequestRecord,
) -> tuple[QuoteWorkflow, FakeQuoteWriteRepository, FakeOutboundReplyRepository]:
    quote_repository = FakeQuoteWriteRepository()
    outbound_repository = FakeOutboundReplyRepository()
    operational_queries = OperationalQueries(FakeOperationalReadRepository(requests=[request]))
    return (
        QuoteWorkflow(quote_repository, outbound_repository, operational_queries),
        quote_repository,
        outbound_repository,
    )


def test_matching_rate_profile_uses_default_markup_when_no_contact() -> None:
    request = RequestRecord(
        id="req-1",
        public_id="REQ-0001",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="parsed",
        weight_kg=500,
    )
    quote_workflow, quote_repository, outbound_repository = _quote_workflow(request)
    profile = RateProfileRecord(
        id="rate-1",
        mode="ltl",
        origin=None,
        destination=None,
        base_price=100,
        price_per_kg=2,
        currency="SEK",
    )
    task_repository = FakeOperationalTaskWriteRepository()
    engine = PricingEngine(
        FakeRateProfileRepository(profile),
        quote_workflow,
        task_repository,
        default_markup_percent=15,
        carrier_rfq_targeting=FakeCarrierRfqTargeting(),
        carrier_rfqs=FakeCarrierRfqRepository(),
        carrier_rfq_outbound=FakeCarrierRfqOutboundRepository(),
        request_repository=FakeRequestWriteRepository(),
    )

    async def run():
        return await engine.price_and_quote(
            PriceAndQuoteCommand(
                request_id="req-1",
                mode="ltl",
                origin="Gothenburg",
                destination="Malmo",
                total_weight_kg=500,
                contact=None,
                recipient_email="customer@example.com",
            )
        )

    result = anyio.run(run)

    # carrier_cost = 100 + 2*500 = 1100; customer_price = 1100 * 1.15 = 1265.0
    assert result.priced is True
    assert result.quote is not None
    assert result.quote.customer_price == 1265.0
    assert result.quote.status == "sent"
    assert outbound_repository.enqueued[0].recipient == "customer@example.com"
    assert task_repository.created == []


def test_matching_rate_profile_prefers_contact_markup() -> None:
    request = RequestRecord(
        id="req-1",
        public_id="REQ-0001",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="parsed",
        weight_kg=500,
    )
    quote_workflow, _, _ = _quote_workflow(request)
    profile = RateProfileRecord(
        id="rate-1",
        mode="ltl",
        origin=None,
        destination=None,
        base_price=100,
        price_per_kg=2,
        currency="SEK",
    )
    engine = PricingEngine(
        FakeRateProfileRepository(profile),
        quote_workflow,
        FakeOperationalTaskWriteRepository(),
        default_markup_percent=15,
        carrier_rfq_targeting=FakeCarrierRfqTargeting(),
        carrier_rfqs=FakeCarrierRfqRepository(),
        carrier_rfq_outbound=FakeCarrierRfqOutboundRepository(),
        request_repository=FakeRequestWriteRepository(),
    )
    contact = ContactRecord(
        id="cnt-1",
        public_id="CNT-0001",
        display_name="Acme",
        email="ops@acme.example",
        domain="acme.example",
        default_markup_percent=20,
        default_incoterms=None,
        payment_terms=None,
    )

    async def run():
        return await engine.price_and_quote(
            PriceAndQuoteCommand(
                request_id="req-1",
                mode="ltl",
                origin="Gothenburg",
                destination="Malmo",
                total_weight_kg=500,
                contact=contact,
                recipient_email="ops@acme.example",
            )
        )

    result = anyio.run(run)

    # carrier_cost = 1100; customer_price = 1100 * 1.20 = 1320.0
    assert result.quote.customer_price == 1320.0


def test_missing_rate_profile_and_no_carriers_escalates_to_task() -> None:
    request = RequestRecord(
        id="req-1",
        public_id="REQ-0001",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="parsed",
        weight_kg=500,
    )
    quote_workflow, quote_repository, outbound_repository = _quote_workflow(request)
    task_repository = FakeOperationalTaskWriteRepository()
    carrier_rfqs = FakeCarrierRfqRepository()
    carrier_rfq_outbound = FakeCarrierRfqOutboundRepository()
    request_repository = FakeRequestWriteRepository()
    engine = PricingEngine(
        FakeRateProfileRepository(None),
        quote_workflow,
        task_repository,
        default_markup_percent=15,
        # No eligible/emailed carriers to RFQ - the last-resort human escalation.
        carrier_rfq_targeting=FakeCarrierRfqTargeting(targets=[]),
        carrier_rfqs=carrier_rfqs,
        carrier_rfq_outbound=carrier_rfq_outbound,
        request_repository=request_repository,
    )

    async def run():
        return await engine.price_and_quote(
            PriceAndQuoteCommand(
                request_id="req-1",
                mode="ltl",
                origin="Gothenburg",
                destination="Malmo",
                total_weight_kg=500,
                contact=None,
                recipient_email="customer@example.com",
            )
        )

    result = anyio.run(run)

    assert result.priced is False
    assert result.quote is None
    assert result.rfq_batch == ()
    assert quote_repository.quotes == {}
    assert outbound_repository.enqueued == []
    assert carrier_rfqs.created_batches == []
    assert carrier_rfq_outbound.enqueued == []
    assert request_repository.status_updates == []
    assert task_repository.created == [
        {"entity_type": "transport_request", "entity_id": "req-1", "reason": NO_CARRIERS_REASON}
    ]


def test_missing_rate_profile_with_carriers_starts_rfq_sourcing() -> None:
    request = RequestRecord(
        id="req-1",
        public_id="REQ-0001",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="parsed",
        weight_kg=500,
    )
    quote_workflow, quote_repository, outbound_repository = _quote_workflow(request)
    task_repository = FakeOperationalTaskWriteRepository()
    carrier_rfqs = FakeCarrierRfqRepository()
    carrier_rfq_outbound = FakeCarrierRfqOutboundRepository()
    request_repository = FakeRequestWriteRepository()
    carrier_a = CarrierRecord(
        id="car-1",
        display_name="Nordic Freight",
        aliases=(),
        modes=("ltl",),
        lane_score=90,
        max_weight_kg=None,
        performance_score=None,
        preferred=False,
        sample_size=0,
        email="rates@nordic.example",
    )
    carrier_b = CarrierRecord(
        id="car-2",
        display_name="Baltic Logistics",
        aliases=(),
        modes=("ltl",),
        lane_score=80,
        max_weight_kg=None,
        performance_score=None,
        preferred=False,
        sample_size=0,
        email="rates@baltic.example",
    )
    engine = PricingEngine(
        FakeRateProfileRepository(None),
        quote_workflow,
        task_repository,
        default_markup_percent=15,
        carrier_rfq_targeting=FakeCarrierRfqTargeting(targets=[carrier_a, carrier_b]),
        carrier_rfqs=carrier_rfqs,
        carrier_rfq_outbound=carrier_rfq_outbound,
        request_repository=request_repository,
    )

    async def run():
        return await engine.price_and_quote(
            PriceAndQuoteCommand(
                request_id="req-1",
                mode="ltl",
                origin="Gothenburg",
                destination="Malmo",
                total_weight_kg=500,
                contact=None,
                recipient_email="customer@example.com",
            )
        )

    result = anyio.run(run)

    # No quote yet - carriers were RFQ'd instead of pricing off a rate_profile.
    assert result.priced is False
    assert result.quote is None
    assert len(result.rfq_batch) == 2
    assert quote_repository.quotes == {}
    assert outbound_repository.enqueued == []
    assert task_repository.created == []

    assert carrier_rfqs.created_batches == [
        {"request_id": "req-1", "carrier_ids": ("car-1", "car-2")}
    ]
    assert {item.recipient for item in carrier_rfq_outbound.enqueued} == {
        "rates@nordic.example",
        "rates@baltic.example",
    }
    for item in carrier_rfq_outbound.enqueued:
        assert "QiNora RFQ #" in item.subject
        assert "Gothenburg" in item.subject
        assert "Malmo" in item.subject

    assert request_repository.status_updates == [("req-1", "sourcing")]
