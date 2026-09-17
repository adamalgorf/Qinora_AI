"""Unit tests for BookingWorkflow.book_quote() - specifically the
request_id override and winning-carrier notification added after a live
incident (2026-09-17, see BookQuoteCommand.request_id's docstring): a
quote's own request_id ended up NULL in the database, which silently broke
finding the winning carrier RFQ (find_winning() needs a real request_id)
and skipped the booking confirmation entirely (status fell back to
"needs_review" instead of "booked"). No dedicated test file existed for
this module before that incident.
"""

from dataclasses import dataclass, field

import anyio

from qinora.application.booking_workflow import BookingWorkflow, BookQuoteCommand
from qinora.application.read_models import (
    CarrierRecord,
    CarrierRfqRecord,
    InboundEmailRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentRecord,
)


@dataclass
class FakeQuoteWriteRepository:
    quote: QuoteRecord

    async def create_quote(self, *, request_id, customer_price, currency):
        raise NotImplementedError

    async def get_quote(self, quote_id):
        raise NotImplementedError

    async def get_quote_record(self, quote_id):
        return self.quote

    async def mark_quote_sent(self, quote_id):
        raise NotImplementedError

    async def mark_quote_accepted(self, quote_id):
        return self.quote

    async def mark_quote_rejected(self, quote_id):
        raise NotImplementedError


@dataclass
class FakeShipmentWriteRepository:
    created: list = field(default_factory=list)

    async def get_shipment(self, shipment_id):
        raise NotImplementedError

    async def create_shipment(self, *, quote_id, carrier_id, lane, status, eta):
        shipment = ShipmentRecord(
            id=f"shp-{len(self.created) + 1}",
            public_id=f"SHP-{len(self.created) + 1:04d}",
            quote_id=quote_id,
            carrier_id=carrier_id,
            lane=lane,
            status=status,
            eta=eta,
        )
        self.created.append(shipment)
        return shipment

    async def update_status(self, shipment_id, status):
        raise NotImplementedError


@dataclass
class FakeIntelligenceResult:
    selected_carrier_id: str | None
    requires_manual_review: bool
    overall_confidence: float


@dataclass
class FakeOperationalQueries:
    requests: list[RequestRecord] = field(default_factory=list)
    carriers: list[CarrierRecord] = field(default_factory=list)
    # None means "the test asserts find_winning() is used instead, so this
    # generic carrier-scoring fallback must never be reached" - raises if
    # called unexpectedly. Set it to exercise the no-winning-rfq fallback.
    fallback_intelligence: FakeIntelligenceResult | None = None
    intelligence_calls: list = field(default_factory=list)

    async def list_requests(self):
        return self.requests

    async def list_carriers(self):
        return self.carriers

    async def run_carrier_intelligence(self, command):
        self.intelligence_calls.append(command)
        if self.fallback_intelligence is None:
            raise NotImplementedError("test never expects the generic fallback to run")
        return self.fallback_intelligence


@dataclass
class FakeCarrierRfqRepository:
    winning_by_request: dict = field(default_factory=dict)
    lookups: list = field(default_factory=list)

    async def create_batch(self, *, request_id, carrier_ids, window_hours=24):
        raise NotImplementedError

    async def find_by_token(self, token):
        raise NotImplementedError

    async def find_by_carrier_email(self, sender_address):
        raise NotImplementedError

    async def find_winning(self, request_id):
        self.lookups.append(request_id)
        return self.winning_by_request.get(request_id)


@dataclass
class FakeOutboundReplyRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue_quote(
        self,
        *,
        quote_id,
        recipient,
        subject,
        body_text,
        in_reply_to_message_id=None,
        sender_mailbox=None,
    ):
        self.enqueued.append(
            {
                "quote_id": quote_id,
                "recipient": recipient,
                "subject": subject,
                "body_text": body_text,
                "sender_mailbox": sender_mailbox,
            }
        )

    async def next_queued(self, limit):
        raise NotImplementedError

    async def mark_sent(self, reply_id):
        raise NotImplementedError

    async def mark_failed(self, reply_id, error_message):
        raise NotImplementedError


@dataclass
class FakeCarrierRfqOutboundRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue(self, *, carrier_rfq_id, recipient, subject, body_text, sender_mailbox=None):
        self.enqueued.append(
            {
                "carrier_rfq_id": carrier_rfq_id,
                "recipient": recipient,
                "subject": subject,
                "body_text": body_text,
                "sender_mailbox": sender_mailbox,
            }
        )

    async def next_queued(self, limit):
        raise NotImplementedError


@dataclass
class FakeEmailThreadRepository:
    history: list[InboundEmailRecord] = field(default_factory=list)

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

    async def link_quote_to_request(self, request_id, quote_id):
        raise NotImplementedError


def _quote(request_id: str | None) -> QuoteRecord:
    return QuoteRecord(
        id="quo-1",
        status="sent",
        version=1,
        customer_price=2420.0,
        currency="SEK",
        parent_quote_id=None,
        request_id=request_id,
    )


def _request(request_id: str = "req-1") -> RequestRecord:
    return RequestRecord(
        id=request_id,
        public_id="REQ-0001",
        customer="Acme AB",
        lane="Göteborg -> Hamburg",
        mode="ltl",
        status="sourcing",
        weight_kg=500.0,
    )


def _winning_rfq(request_id: str, carrier_id: str = "car-1") -> CarrierRfqRecord:
    return CarrierRfqRecord(
        id="rfq-1",
        request_id=request_id,
        carrier_id=carrier_id,
        correlation_token="tok-1",
        status="responded",
        sent_at="2026-09-17T08:00:00",
        responded_at="2026-09-17T09:00:00",
        expires_at="2026-09-18T08:00:00",
    )


def _carrier(carrier_id: str = "car-1", email: str | None = "carrier@example.com") -> CarrierRecord:
    return CarrierRecord(
        id=carrier_id,
        display_name="Qinora",
        aliases=(),
        modes=("ltl",),
        lane_score=80.0,
        max_weight_kg=None,
        performance_score=None,
        preferred=True,
        sample_size=1,
        email=email,
    )


def _workflow(
    *,
    quote: QuoteRecord,
    requests: list[RequestRecord],
    carriers: list[CarrierRecord],
    winning_by_request: dict,
    carrier_rfq_outbound: FakeCarrierRfqOutboundRepository | None = None,
    carrier_mailbox: str | None = "carrier@sandahls.com",
    fallback_intelligence: FakeIntelligenceResult | None = None,
):
    quote_repo = FakeQuoteWriteRepository(quote=quote)
    shipment_repo = FakeShipmentWriteRepository()
    operational_queries = FakeOperationalQueries(
        requests=requests, carriers=carriers, fallback_intelligence=fallback_intelligence
    )
    carrier_rfqs = FakeCarrierRfqRepository(winning_by_request=winning_by_request)
    outbound_repo = FakeOutboundReplyRepository()
    workflow = BookingWorkflow(
        quote_repository=quote_repo,
        shipment_repository=shipment_repo,
        operational_queries=operational_queries,
        carrier_rfqs=carrier_rfqs,
        outbound_repository=outbound_repo,
        email_threads=FakeEmailThreadRepository(),
        customer_mailbox="test.spedition@sandahls.com",
        carrier_rfq_outbound=carrier_rfq_outbound,
        carrier_mailbox=carrier_mailbox,
    )
    return workflow, shipment_repo, carrier_rfqs, outbound_repo


def test_command_request_id_is_used_to_find_the_winning_rfq_when_quote_request_id_is_null():
    quote = _quote(request_id=None)
    winning = _winning_rfq("req-1")
    workflow, shipment_repo, carrier_rfqs, outbound_repo = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier()],
        winning_by_request={"req-1": winning},
    )
    command = BookQuoteCommand(
        quote_id="quo-1",
        mode="ltl",
        total_weight_kg=500.0,
        request_id="req-1",
    )

    result = anyio.run(workflow.book_quote, command)

    assert carrier_rfqs.lookups == ["req-1"]
    assert result.selected_carrier_id == "car-1"
    assert result.requires_manual_review is False
    assert shipment_repo.created[0].status == "booked"


def test_falls_back_to_quote_request_id_when_command_request_id_not_given():
    quote = _quote(request_id="req-2")
    winning = _winning_rfq("req-2")
    workflow, shipment_repo, carrier_rfqs, outbound_repo = _workflow(
        quote=quote,
        requests=[_request("req-2")],
        carriers=[_carrier()],
        winning_by_request={"req-2": winning},
    )
    command = BookQuoteCommand(quote_id="quo-1", mode="ltl", total_weight_kg=500.0)

    result = anyio.run(workflow.book_quote, command)

    assert carrier_rfqs.lookups == ["req-2"]
    assert result.selected_carrier_id == "car-1"
    assert shipment_repo.created[0].status == "booked"


def test_booking_confirmation_to_customer_includes_the_shipment_id():
    quote = _quote(request_id=None)
    workflow, shipment_repo, _, outbound_repo = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier()],
        winning_by_request={"req-1": _winning_rfq("req-1")},
    )
    command = BookQuoteCommand(
        quote_id="quo-1",
        mode="ltl",
        total_weight_kg=500.0,
        request_id="req-1",
        recipient_email="kund@example.com",
    )

    anyio.run(workflow.book_quote, command)

    assert len(outbound_repo.enqueued) == 1
    reply = outbound_repo.enqueued[0]
    shipment = shipment_repo.created[0]
    assert reply["recipient"] == "kund@example.com"
    assert shipment.public_id in reply["body_text"]
    assert f"Frakt-ID: {shipment.public_id}" in reply["body_text"]


def test_winning_carrier_is_notified_to_proceed_once_booked():
    carrier_rfq_outbound = FakeCarrierRfqOutboundRepository()
    quote = _quote(request_id=None)
    workflow, shipment_repo, _, _ = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier(carrier_id="car-1", email="carrier@example.com")],
        winning_by_request={"req-1": _winning_rfq("req-1", carrier_id="car-1")},
        carrier_rfq_outbound=carrier_rfq_outbound,
    )
    command = BookQuoteCommand(
        quote_id="quo-1", mode="ltl", total_weight_kg=500.0, request_id="req-1"
    )

    anyio.run(workflow.book_quote, command)

    assert len(carrier_rfq_outbound.enqueued) == 1
    notice = carrier_rfq_outbound.enqueued[0]
    shipment = shipment_repo.created[0]
    assert notice["carrier_rfq_id"] == "rfq-1"
    assert notice["recipient"] == "carrier@example.com"
    assert notice["subject"] == f"Bokning bekräftad - {shipment.public_id}"
    assert shipment.public_id in notice["body_text"]
    assert notice["sender_mailbox"] == "carrier@sandahls.com"


def test_carrier_notification_skipped_when_outbound_queue_not_wired():
    quote = _quote(request_id=None)
    workflow, shipment_repo, _, _ = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier()],
        winning_by_request={"req-1": _winning_rfq("req-1")},
        carrier_rfq_outbound=None,
    )
    command = BookQuoteCommand(
        quote_id="quo-1", mode="ltl", total_weight_kg=500.0, request_id="req-1"
    )

    result = anyio.run(workflow.book_quote, command)

    assert shipment_repo.created[0].status == "booked"
    assert result.requires_manual_review is False


def test_carrier_notification_skipped_when_carrier_has_no_email_on_file():
    carrier_rfq_outbound = FakeCarrierRfqOutboundRepository()
    quote = _quote(request_id=None)
    workflow, _, _, _ = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier(carrier_id="car-1", email=None)],
        winning_by_request={"req-1": _winning_rfq("req-1", carrier_id="car-1")},
        carrier_rfq_outbound=carrier_rfq_outbound,
    )
    command = BookQuoteCommand(
        quote_id="quo-1", mode="ltl", total_weight_kg=500.0, request_id="req-1"
    )

    anyio.run(workflow.book_quote, command)

    assert carrier_rfq_outbound.enqueued == []


def test_carrier_notification_skipped_when_there_is_no_winning_rfq():
    carrier_rfq_outbound = FakeCarrierRfqOutboundRepository()
    quote = _quote(request_id=None)
    workflow, shipment_repo, carrier_rfqs, _ = _workflow(
        quote=quote,
        requests=[_request("req-1")],
        carriers=[_carrier()],
        winning_by_request={},
        carrier_rfq_outbound=carrier_rfq_outbound,
        fallback_intelligence=FakeIntelligenceResult(
            selected_carrier_id="car-1", requires_manual_review=False, overall_confidence=0.9
        ),
    )
    command = BookQuoteCommand(
        quote_id="quo-1", mode="ltl", total_weight_kg=500.0, request_id="req-1"
    )

    anyio.run(workflow.book_quote, command)

    assert carrier_rfqs.lookups == ["req-1"]
    assert shipment_repo.created[0].status == "booked"
    assert carrier_rfq_outbound.enqueued == []
