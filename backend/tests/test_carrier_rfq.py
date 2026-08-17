"""Covers the new carrier-RFQ round trip added on top of the shipped
email-intake-auto-quote-flow pass:

  - CarrierRfqTargeting (application/carrier_rfq.py) - picks eligible,
    emailed carriers as RFQ targets.
  - Correlation token round trip - create_batch() then find_by_token()
    against an in-memory CarrierRfqRepository implementation (this repo has
    no real-database-backed repository test harness to extend, so this
    exercises the port's contract rather than the SQLite/Postgres SQL
    itself - see infrastructure/sqlite.py's SQLiteCarrierRfqRepository and
    infrastructure/postgres.py's PostgresCarrierRfqRepository for those).
  - CarrierRfqCollector (application/carrier_rfq_collector.py) - cheapest
    offer wins, the rest get superseded; zero responses escalates to a
    human task instead of a silent failure.

application/pricing_engine.py's own "zero eligible/emailed carriers ->
escalate to a human task" branch (the other half of "zero-carrier-available
escalates to a task") is covered in test_pricing_engine.py's
test_missing_rate_profile_and_no_carriers_escalates_to_task, since that's
where the escalation actually happens - this file's
test_targeting_returns_nothing_when_no_carrier_has_email covers the
targeting half of that same scenario.
"""

import secrets
from dataclasses import dataclass, field, replace

import anyio

from qinora.application.carrier_rfq import CarrierRfqTargeting, SelectRfqTargetsCommand
from qinora.application.carrier_rfq_collector import (
    NO_RESPONSE_REASON,
    CarrierRfqCollector,
    CollectCarrierRfqsCommand,
)
from qinora.application.operational_queries import OperationalQueries
from qinora.application.quote_workflow import QuoteWorkflow
from qinora.application.read_models import (
    CarrierOfferRecord,
    CarrierRecord,
    CarrierRfqRecord,
    ContactRecord,
    InboundEmailRecord,
    OutboundReplyRecord,
    QuoteRecord,
    RequestRecord,
)
from qinora.domain import CurrencyCode, Money, Quote, QuoteStatus

# --- shared fakes -------------------------------------------------------


@dataclass
class FakeCarrierListRepository:
    """A minimal OperationalReadRepository stub - CarrierRfqTargeting only
    ever calls list_carriers(), everything else is unused and would raise.
    """

    carriers: list

    async def list_requests(self):
        raise NotImplementedError

    async def get_request_detail(self, request_id):
        raise NotImplementedError

    async def list_quotes(self):
        raise NotImplementedError

    async def get_quote_detail(self, quote_id):
        raise NotImplementedError

    async def list_shipments(self):
        raise NotImplementedError

    async def list_invoices(self):
        raise NotImplementedError

    async def list_carriers(self):
        return self.carriers

    async def list_contacts(self):
        raise NotImplementedError

    async def list_inbox(self):
        raise NotImplementedError

    async def get_inbox_detail(self, message_id):
        raise NotImplementedError

    async def list_agent_logs(self):
        raise NotImplementedError

    async def list_operational_tasks(self):
        raise NotImplementedError

    async def list_shipment_events(self, shipment_id):
        raise NotImplementedError

    async def list_outbound_replies(self):
        raise NotImplementedError


@dataclass
class InMemoryCarrierRfqRepository:
    """A small, correct CarrierRfqRepository implementation (application/ports.py)
    used to exercise the correlation-token round trip at the port-contract
    level - one row and one unique short-hex token per carrier, findable
    back by that token.
    """

    _rows: dict = field(default_factory=dict)
    _by_token: dict = field(default_factory=dict)

    async def create_batch(self, *, request_id, carrier_ids, window_hours=24):
        records = []
        for carrier_id in carrier_ids:
            token = secrets.token_hex(4)
            while token in self._by_token:
                token = secrets.token_hex(4)
            record_id = f"rfq-{len(self._rows) + 1}"
            record = CarrierRfqRecord(
                id=record_id,
                request_id=request_id,
                carrier_id=carrier_id,
                correlation_token=token,
                status="sent",
                sent_at="2026-01-01T00:00:00",
                responded_at=None,
                expires_at="2026-01-02T00:00:00",
            )
            self._rows[record_id] = record
            self._by_token[token] = record_id
            records.append(record)
        return records

    async def find_by_token(self, token):
        record_id = self._by_token.get(token)
        return self._rows.get(record_id) if record_id else None

    async def find_by_carrier_email(self, sender_address):
        raise NotImplementedError

    async def mark_responded(self, rfq_id, offer_id):
        raise NotImplementedError

    async def list_open_batch(self, request_id):
        return [row for row in self._rows.values() if row.request_id == request_id]

    async def list_batch(self, request_id):
        return [row for row in self._rows.values() if row.request_id == request_id]

    async def expire_stale(self, cutoff):
        raise NotImplementedError

    async def mark_superseded(self, rfq_ids):
        for rfq_id in rfq_ids:
            row = self._rows.get(rfq_id)
            if row is not None:
                self._rows[rfq_id] = replace(row, status="superseded")


@dataclass
class FakeCollectorCarrierRfqRepository:
    batch: list = field(default_factory=list)
    superseded: tuple = ()
    expired_result: list = field(default_factory=list)

    async def create_batch(self, *, request_id, carrier_ids, window_hours=24):
        raise NotImplementedError

    async def find_by_token(self, token):
        raise NotImplementedError

    async def find_by_carrier_email(self, sender_address):
        raise NotImplementedError

    async def mark_responded(self, rfq_id, offer_id):
        raise NotImplementedError

    async def list_open_batch(self, request_id):
        return [row for row in self.batch if row.status == "sent"]

    async def list_batch(self, request_id):
        return list(self.batch)

    async def expire_stale(self, cutoff):
        return self.expired_result

    async def mark_superseded(self, rfq_ids):
        self.superseded = tuple(rfq_ids)


@dataclass
class FakeCollectorCarrierOfferRepository:
    offers: list = field(default_factory=list)

    async def create_offer(self, **kwargs):
        raise NotImplementedError

    async def list_offers_for_request(self, request_id):
        return [offer for offer in self.offers if offer.request_id == request_id]


@dataclass
class FakeCollectorEmailThreadRepository:
    history: list = field(default_factory=list)

    async def get(self, email_id):
        raise NotImplementedError

    async def find_candidates_by_message_ids(self, message_ids):
        raise NotImplementedError

    async def find_candidates_by_sender(self, sender, limit=200):
        raise NotImplementedError

    async def find_candidates_by_domain(self, domain, limit=200):
        raise NotImplementedError

    async def list_thread_history(self, *, request_id, quote_id):
        return self.history

    async def link_thread(self, email_id, *, request_id, quote_id):
        raise NotImplementedError

    async def mark_classification(self, email_id, classification):
        raise NotImplementedError


@dataclass
class FakeCollectorContactReadRepository:
    contact: ContactRecord | None = None

    async def find_by_sender(self, sender):
        return self.contact


@dataclass
class FakeTaskRepository:
    created: list = field(default_factory=list)

    async def create_task(self, *, entity_type, entity_id, reason, priority="normal"):
        self.created.append({"entity_type": entity_type, "entity_id": entity_id, "reason": reason})
        return None


@dataclass
class FakeRequestStatusRepository:
    status_updates: list = field(default_factory=list)

    async def create_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_request_status(self, request_id, status):
        self.status_updates.append((request_id, status))


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
class FakeRequestsOnlyRepository:
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


def _quote_workflow(request: RequestRecord):
    quote_repository = FakeQuoteWriteRepository()
    outbound_repository = FakeOutboundReplyRepository()
    operational_queries = OperationalQueries(FakeRequestsOnlyRepository(requests=[request]))
    return (
        QuoteWorkflow(quote_repository, outbound_repository, operational_queries),
        quote_repository,
        outbound_repository,
    )


def _carrier(carrier_id: str, *, modes=("ltl",), lane_score=90, email="rates@example.com"):
    return CarrierRecord(
        id=carrier_id,
        display_name=carrier_id,
        aliases=(),
        modes=modes,
        lane_score=lane_score,
        max_weight_kg=None,
        performance_score=None,
        preferred=False,
        sample_size=0,
        email=email,
    )


# --- CarrierRfqTargeting -------------------------------------------------


def test_targeting_picks_eligible_carriers_with_email_only() -> None:
    carriers = [
        _carrier("car-1", lane_score=90, email="rates@nordic.example"),
        _carrier("car-2", lane_score=95, email=None),  # no email - never RFQ'd
        _carrier("car-3", modes=("air",), email="rates@air.example"),  # wrong mode
    ]
    operational_queries = OperationalQueries(FakeCarrierListRepository(carriers))
    targeting = CarrierRfqTargeting(operational_queries)

    async def run():
        return await targeting.select_targets(
            SelectRfqTargetsCommand(mode="ltl", total_weight_kg=500)
        )

    targets = anyio.run(run)

    assert [carrier.id for carrier in targets] == ["car-1"]


def test_targeting_returns_nothing_when_no_carrier_has_email() -> None:
    carriers = [_carrier("car-1", email=None)]
    operational_queries = OperationalQueries(FakeCarrierListRepository(carriers))
    targeting = CarrierRfqTargeting(operational_queries)

    async def run():
        return await targeting.select_targets(
            SelectRfqTargetsCommand(mode="ltl", total_weight_kg=500)
        )

    assert anyio.run(run) == ()


def test_targeting_respects_max_targets_and_ranks_by_score() -> None:
    carriers = [_carrier(f"car-{i}", lane_score=100 - i) for i in range(5)]
    operational_queries = OperationalQueries(FakeCarrierListRepository(carriers))
    targeting = CarrierRfqTargeting(operational_queries)

    async def run():
        return await targeting.select_targets(
            SelectRfqTargetsCommand(mode="ltl", total_weight_kg=500, max_targets=2)
        )

    targets = anyio.run(run)

    assert len(targets) == 2
    assert targets[0].id == "car-0"  # highest lane_score wins first


# --- correlation token round trip ----------------------------------------


def test_correlation_token_round_trip_create_batch_then_find_by_token() -> None:
    repository = InMemoryCarrierRfqRepository()

    async def run():
        created = await repository.create_batch(request_id="req-1", carrier_ids=("car-1", "car-2"))
        found = [await repository.find_by_token(record.correlation_token) for record in created]
        return created, found

    created, found = anyio.run(run)

    assert len(created) == 2
    assert created[0].correlation_token != created[1].correlation_token
    assert all(len(record.correlation_token) == 8 for record in created)
    assert found == created
    assert all(record.request_id == "req-1" for record in found)


# --- CarrierRfqCollector ---------------------------------------------------


def test_collector_prices_cheapest_offer_and_supersedes_the_rest() -> None:
    request = RequestRecord(
        id="req-1",
        public_id="REQ-0001",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="sourcing",
        weight_kg=500,
    )
    quote_workflow, quote_repository, outbound_repository = _quote_workflow(request)

    batch = [
        CarrierRfqRecord(
            id="rfq-1",
            request_id="req-1",
            carrier_id="car-1",
            correlation_token="tok1",
            status="responded",
            sent_at="2026-01-01T00:00:00",
            responded_at="2026-01-01T01:00:00",
            expires_at="2026-01-02T00:00:00",
        ),
        CarrierRfqRecord(
            id="rfq-2",
            request_id="req-1",
            carrier_id="car-2",
            correlation_token="tok2",
            status="responded",
            sent_at="2026-01-01T00:00:00",
            responded_at="2026-01-01T02:00:00",
            expires_at="2026-01-02T00:00:00",
        ),
    ]
    offers = [
        CarrierOfferRecord(
            id="offer-1",
            request_id="req-1",
            carrier_name="Nordic Freight",
            price=1000.0,
            currency="SEK",
            transit_days=2,
            notes=None,
            confidence=0.9,
            created_at="2026-01-01T01:00:00",
            carrier_rfq_id="rfq-1",
        ),
        CarrierOfferRecord(
            id="offer-2",
            request_id="req-1",
            carrier_name="Baltic Logistics",
            price=800.0,  # cheapest - should win
            currency="SEK",
            transit_days=3,
            notes=None,
            confidence=0.9,
            created_at="2026-01-01T02:00:00",
            carrier_rfq_id="rfq-2",
        ),
    ]
    carrier_rfqs = FakeCollectorCarrierRfqRepository(batch=batch)
    carrier_offers = FakeCollectorCarrierOfferRepository(offers=offers)
    email_threads = FakeCollectorEmailThreadRepository(
        history=[
            InboundEmailRecord(
                id="mail-1",
                sender="ops@acme.example",
                recipient="farah@qinora.org",
                subject="RFQ Gothenburg -> Malmo",
                body_text="...",
                classification="transport_request",
                message_id=None,
                in_reply_to=None,
                references_header=None,
                request_id="req-1",
                quote_id=None,
                created_at="2026-01-01T00:00:00",
            )
        ]
    )
    task_repository = FakeTaskRepository()
    request_repository = FakeRequestStatusRepository()

    collector = CarrierRfqCollector(
        carrier_rfqs,
        carrier_offers,
        email_threads,
        FakeCollectorContactReadRepository(contact=None),
        quote_workflow,
        task_repository,
        request_repository,
        default_markup_percent=10,
    )

    outcome = anyio.run(lambda: collector.finalize_batch("req-1"))

    assert outcome is not None
    assert outcome.escalated is False
    assert outcome.quote is not None
    # cheapest offer wins: carrier_cost 800 SEK * 1.10 default markup = 880.0
    assert outcome.quote.customer_price == 880.0
    assert outcome.quote.status == "sent"
    assert outbound_repository.enqueued[0].recipient == "ops@acme.example"
    assert carrier_rfqs.superseded == ("rfq-1",)  # the pricier one lost
    assert request_repository.status_updates == [("req-1", "quoted")]
    assert task_repository.created == []


def test_collector_prefers_contact_markup_over_default() -> None:
    request = RequestRecord(
        id="req-2",
        public_id="REQ-0002",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="sourcing",
        weight_kg=500,
    )
    quote_workflow, _quote_repository, _outbound_repository = _quote_workflow(request)

    batch = [
        CarrierRfqRecord(
            id="rfq-3",
            request_id="req-2",
            carrier_id="car-1",
            correlation_token="tok3",
            status="responded",
            sent_at="2026-01-01T00:00:00",
            responded_at="2026-01-01T01:00:00",
            expires_at="2026-01-02T00:00:00",
        ),
    ]
    offers = [
        CarrierOfferRecord(
            id="offer-3",
            request_id="req-2",
            carrier_name="Nordic Freight",
            price=1000.0,
            currency="SEK",
            transit_days=2,
            notes=None,
            confidence=0.9,
            created_at="2026-01-01T01:00:00",
            carrier_rfq_id="rfq-3",
        ),
    ]
    contact = ContactRecord(
        id="cnt-1",
        public_id="CNT-0001",
        display_name="Acme",
        email="ops@acme.example",
        domain="acme.example",
        default_markup_percent=25,
        default_incoterms=None,
        payment_terms=None,
    )
    collector = CarrierRfqCollector(
        FakeCollectorCarrierRfqRepository(batch=batch),
        FakeCollectorCarrierOfferRepository(offers=offers),
        FakeCollectorEmailThreadRepository(
            history=[
                InboundEmailRecord(
                    id="mail-2",
                    sender="ops@acme.example",
                    recipient="farah@qinora.org",
                    subject="RFQ",
                    body_text="...",
                    classification="transport_request",
                    message_id=None,
                    in_reply_to=None,
                    references_header=None,
                    request_id="req-2",
                    quote_id=None,
                    created_at="2026-01-01T00:00:00",
                )
            ]
        ),
        FakeCollectorContactReadRepository(contact=contact),
        quote_workflow,
        FakeTaskRepository(),
        FakeRequestStatusRepository(),
        default_markup_percent=10,
    )

    outcome = anyio.run(lambda: collector.finalize_batch("req-2"))

    # carrier_cost 1000 SEK * 1.25 contact markup = 1250.0, not the 10% default.
    assert outcome.quote.customer_price == 1250.0


def test_collector_escalates_when_batch_closes_with_zero_responses() -> None:
    request = RequestRecord(
        id="req-3",
        public_id="REQ-0003",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="sourcing",
        weight_kg=500,
    )
    quote_workflow, quote_repository, outbound_repository = _quote_workflow(request)

    batch = [
        CarrierRfqRecord(
            id="rfq-4",
            request_id="req-3",
            carrier_id="car-1",
            correlation_token="tok4",
            status="expired",
            sent_at="2026-01-01T00:00:00",
            responded_at=None,
            expires_at="2026-01-02T00:00:00",
        ),
    ]
    task_repository = FakeTaskRepository()
    request_repository = FakeRequestStatusRepository()

    collector = CarrierRfqCollector(
        FakeCollectorCarrierRfqRepository(batch=batch),
        FakeCollectorCarrierOfferRepository(offers=[]),
        FakeCollectorEmailThreadRepository(history=[]),
        FakeCollectorContactReadRepository(),
        quote_workflow,
        task_repository,
        request_repository,
        default_markup_percent=10,
    )

    outcome = anyio.run(lambda: collector.finalize_batch("req-3"))

    assert outcome is not None
    assert outcome.escalated is True
    assert outcome.quote is None
    assert quote_repository.quotes == {}
    assert outbound_repository.enqueued == []
    assert task_repository.created == [
        {"entity_type": "transport_request", "entity_id": "req-3", "reason": NO_RESPONSE_REASON}
    ]
    assert request_repository.status_updates == []


def test_collector_returns_none_while_batch_still_has_open_rfqs() -> None:
    batch = [
        CarrierRfqRecord(
            id="rfq-5",
            request_id="req-4",
            carrier_id="car-1",
            correlation_token="tok5",
            status="sent",
            sent_at="2026-01-01T00:00:00",
            responded_at=None,
            expires_at="2026-01-02T00:00:00",
        ),
    ]
    collector = CarrierRfqCollector(
        FakeCollectorCarrierRfqRepository(batch=batch),
        FakeCollectorCarrierOfferRepository(offers=[]),
        FakeCollectorEmailThreadRepository(),
        FakeCollectorContactReadRepository(),
        None,  # never touched - finalize_batch bails out before using it
        FakeTaskRepository(),
        FakeRequestStatusRepository(),
        default_markup_percent=10,
    )

    assert anyio.run(lambda: collector.finalize_batch("req-4")) is None


def test_run_expires_stale_rfqs_and_finalizes_affected_batches() -> None:
    request = RequestRecord(
        id="req-5",
        public_id="REQ-0005",
        customer="Acme",
        lane="Gothenburg -> Malmo",
        mode="ltl",
        status="sourcing",
        weight_kg=500,
    )
    quote_workflow, _quote_repository, _outbound_repository = _quote_workflow(request)

    expired_rfq = CarrierRfqRecord(
        id="rfq-6",
        request_id="req-5",
        carrier_id="car-1",
        correlation_token="tok6",
        status="expired",
        sent_at="2026-01-01T00:00:00",
        responded_at=None,
        expires_at="2026-01-02T00:00:00",
    )
    task_repository = FakeTaskRepository()

    collector = CarrierRfqCollector(
        FakeCollectorCarrierRfqRepository(batch=[expired_rfq], expired_result=[expired_rfq]),
        FakeCollectorCarrierOfferRepository(offers=[]),
        FakeCollectorEmailThreadRepository(history=[]),
        FakeCollectorContactReadRepository(),
        quote_workflow,
        task_repository,
        FakeRequestStatusRepository(),
        default_markup_percent=10,
    )

    result = anyio.run(lambda: collector.run(CollectCarrierRfqsCommand(window_hours=24)))

    assert len(result.finalized) == 1
    assert result.finalized[0].request_id == "req-5"
    assert result.finalized[0].escalated is True
    assert task_repository.created == [
        {"entity_type": "transport_request", "entity_id": "req-5", "reason": NO_RESPONSE_REASON}
    ]
