"""Unit tests for the two-phase carrier RFQ finalization split (see
carrier_rfq_collector.py's module docstring): finalize_batch() picks the
cheapest carrier offer and reports it to the customer mailbox by email,
finalize_customer_quote() actually prices and sends the customer quote once
that report email lands. No dedicated test file existed for this module
before 2026-09-16 despite it being the most severe, twice-reproduced live
bug of that day (the customer's own quote getting sent back to qinora.ai@
instead of the customer) - see quote_workflow.py's first_customer_email()
docstring for the full incident history.
"""

from dataclasses import dataclass, field, replace

import anyio

from qinora.application.carrier_rfq_collector import (
    NO_RECIPIENT_REASON,
    NO_RESPONSE_REASON,
    CarrierRfqCollector,
)
from qinora.application.operational_queries import OperationalQueries
from qinora.application.quote_workflow import QuoteWorkflow
from qinora.application.read_models import (
    CarrierOfferRecord,
    CarrierRfqRecord,
    ContactRecord,
    InboundEmailRecord,
    OutboundReplyRecord,
    QuoteRecord,
    RequestRecord,
)
from qinora.domain import CurrencyCode, Money, Quote, QuoteStatus

DEFAULT_MARKUP = 15.0


@dataclass
class FakeCarrierRfqRepository:
    batch: list[CarrierRfqRecord] = field(default_factory=list)
    winning: CarrierRfqRecord | None = None
    superseded: list = field(default_factory=list)

    async def list_batch(self, request_id):
        return self.batch

    async def mark_superseded(self, rfq_ids):
        self.superseded.append(rfq_ids)

    async def find_winning(self, request_id):
        return self.winning


@dataclass
class FakeCarrierOfferWriteRepository:
    offers: list[CarrierOfferRecord] = field(default_factory=list)

    async def create_offer(self, **kwargs):
        raise NotImplementedError

    async def list_offers_for_request(self, request_id):
        return [o for o in self.offers if o.request_id == request_id]


@dataclass
class FakeEmailThreadRepository:
    history: list[InboundEmailRecord] = field(default_factory=list)
    linked_quotes: list = field(default_factory=list)

    async def get(self, email_id):
        raise NotImplementedError

    async def find_candidates_by_message_ids(self, message_ids):
        return []

    async def find_candidates_by_sender(self, sender, limit=200):
        return []

    async def find_candidates_by_domain(self, domain, limit=200):
        return []

    async def list_thread_history(self, *, request_id, quote_id):
        return self.history

    async def link_thread(self, email_id, *, request_id, quote_id):
        raise NotImplementedError

    async def mark_classification(self, email_id, classification):
        raise NotImplementedError

    async def link_quote_to_request(self, request_id, quote_id):
        self.linked_quotes.append((request_id, quote_id))


@dataclass
class FakeContactReadRepository:
    contact: ContactRecord | None = None

    async def find_by_sender(self, sender):
        return self.contact


@dataclass
class FakeOperationalTaskWriteRepository:
    created: list = field(default_factory=list)

    async def create_task(self, *, entity_type, entity_id, reason, priority="normal"):
        self.created.append(
            {"entity_type": entity_type, "entity_id": entity_id, "reason": reason}
        )
        return None


@dataclass
class FakeRequestWriteRepository:
    status_updates: list = field(default_factory=list)

    async def create_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_transport_request(self, **kwargs):
        raise NotImplementedError

    async def update_request_status(self, request_id, status):
        self.status_updates.append((request_id, status))


@dataclass
class FakeCarrierOfferReportOutboundRepository:
    enqueued: list = field(default_factory=list)

    async def enqueue(self, *, request_id, recipient, subject, body_text, sender_mailbox=None):
        self.enqueued.append(
            {
                "request_id": request_id,
                "recipient": recipient,
                "subject": subject,
                "body_text": body_text,
                "sender_mailbox": sender_mailbox,
            }
        )
        return None

    async def next_queued(self, limit):
        raise NotImplementedError

    async def mark_sent(self, item_id):
        raise NotImplementedError

    async def mark_failed(self, item_id, error_message):
        raise NotImplementedError


# --- QuoteWorkflow's own fakes (mirrors test_quote_workflow_threading.py) --


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
    enqueued: list[OutboundReplyRecord] = field(default_factory=list)

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
        record = OutboundReplyRecord(
            id=f"reply-{len(self.enqueued) + 1}",
            quote_id=quote_id,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            status="queued",
            created_at="2026-01-01T00:00:00",
            in_reply_to_message_id=in_reply_to_message_id,
            sender_mailbox=sender_mailbox,
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
    request: RequestRecord

    async def list_requests(self):
        return [self.request]


def _request(request_id: str = "req-1", status: str = "sourcing") -> RequestRecord:
    return RequestRecord(
        id=request_id,
        public_id="REQ-0001",
        customer="Acme AB",
        lane="Gothenburg -> Hamburg",
        mode="ltl",
        status=status,
        weight_kg=500.0,
    )


def _rfq(
    rfq_id: str,
    *,
    request_id: str = "req-1",
    status: str = "responded",
) -> CarrierRfqRecord:
    return CarrierRfqRecord(
        id=rfq_id,
        request_id=request_id,
        carrier_id=f"car-{rfq_id}",
        correlation_token=f"tok-{rfq_id}",
        status=status,
        sent_at="2026-01-01T00:00:00",
        responded_at="2026-01-01T01:00:00",
        expires_at="2026-01-02T00:00:00",
    )


def _offer(
    offer_id: str,
    *,
    request_id: str = "req-1",
    carrier_rfq_id: str,
    price: float | None,
    carrier_name: str = "Nordic Freight",
) -> CarrierOfferRecord:
    return CarrierOfferRecord(
        id=offer_id,
        request_id=request_id,
        carrier_name=carrier_name,
        price=price,
        currency="SEK",
        transit_days=2,
        notes=None,
        confidence=0.9,
        created_at="2026-01-01T01:00:00",
        carrier_rfq_id=carrier_rfq_id,
    )


def _inbound(
    email_id: str,
    *,
    sender: str = "customer@example.com",
    classification: str = "transport_request",
    message_id: str | None = None,
) -> InboundEmailRecord:
    return InboundEmailRecord(
        id=email_id,
        sender=sender,
        recipient="test.spedition@sandahls.com",
        subject="Fraktforfragan",
        body_text="...",
        classification=classification,
        message_id=message_id,
        in_reply_to=None,
        references_header=None,
        request_id="req-1",
        quote_id=None,
        created_at="2026-01-01T00:00:00",
    )


def _build_collector(
    *,
    batch: list[CarrierRfqRecord],
    offers: list[CarrierOfferRecord],
    history: list[InboundEmailRecord] | None = None,
    winning: CarrierRfqRecord | None = None,
    carrier_offer_report_outbound: FakeCarrierOfferReportOutboundRepository | None = None,
    carrier_mailbox: str | None = None,
    customer_mailbox: str | None = None,
    request: RequestRecord | None = None,
    contact: ContactRecord | None = None,
):
    carrier_rfqs = FakeCarrierRfqRepository(batch=batch, winning=winning)
    carrier_offers = FakeCarrierOfferWriteRepository(offers=offers)
    email_threads = FakeEmailThreadRepository(history=history or [])
    contacts = FakeContactReadRepository(contact=contact)

    quote_repo = FakeQuoteWriteRepository()
    outbound = FakeOutboundReplyRepository()
    operational_queries = OperationalQueries(
        FakeOperationalReadRepository(request=request or _request())
    )
    quote_workflow = QuoteWorkflow(
        quote_repo,
        outbound,
        operational_queries,
        email_threads,
        customer_mailbox=customer_mailbox,
    )

    task_repository = FakeOperationalTaskWriteRepository()
    request_repository = FakeRequestWriteRepository()

    collector = CarrierRfqCollector(
        carrier_rfqs,
        carrier_offers,
        email_threads,
        contacts,
        quote_workflow,
        task_repository,
        request_repository,
        default_markup_percent=DEFAULT_MARKUP,
        carrier_offer_report_outbound=carrier_offer_report_outbound,
        carrier_mailbox=carrier_mailbox,
        customer_mailbox=customer_mailbox,
    )
    return collector, {
        "carrier_rfqs": carrier_rfqs,
        "quote_repo": quote_repo,
        "outbound": outbound,
        "task_repository": task_repository,
        "request_repository": request_repository,
        "email_threads": email_threads,
    }


# --- finalize_batch ------------------------------------------------------


def test_finalize_batch_quotes_customer_directly_in_single_mailbox_mode() -> None:
    # No carrier_offer_report_outbound/customer_mailbox configured - the
    # only option is the old direct-quote fallback.
    batch = [_rfq("rfq-1"), _rfq("rfq-2")]
    offers = [
        _offer("off-1", carrier_rfq_id="rfq-1", price=9000.0),
        _offer("off-2", carrier_rfq_id="rfq-2", price=8500.0),
    ]
    history = [_inbound("mail-1")]
    collector, fakes = _build_collector(batch=batch, offers=offers, history=history)

    result = anyio.run(lambda: collector.finalize_batch("req-1"))

    assert result is not None
    assert result.escalated is False
    assert result.quote is not None
    # cheapest = 8500 * 1.15 = 9775.0
    assert result.quote.customer_price == 9775.0
    assert fakes["carrier_rfqs"].superseded == [("rfq-1",)]
    assert fakes["request_repository"].status_updates == [("req-1", "quoted")]


def test_finalize_batch_enqueues_offer_report_in_two_mailbox_mode() -> None:
    # carrier_offer_report_outbound + customer_mailbox configured - reports
    # the winning rate by email instead of quoting the customer directly
    # (see module docstring - the mailbox-to-mailbox hop is a real email).
    batch = [_rfq("rfq-1")]
    offers = [_offer("off-1", carrier_rfq_id="rfq-1", price=8500.0)]
    report_outbound = FakeCarrierOfferReportOutboundRepository()
    collector, fakes = _build_collector(
        batch=batch,
        offers=offers,
        carrier_offer_report_outbound=report_outbound,
        carrier_mailbox="qinora.ai@sandahls.com",
        customer_mailbox="test.spedition@sandahls.com",
    )

    result = anyio.run(lambda: collector.finalize_batch("req-1"))

    assert result is not None
    assert result.escalated is False
    assert result.quote is None
    # No customer quote created yet - only the report email is enqueued.
    assert fakes["quote_repo"].quotes == {}
    assert fakes["request_repository"].status_updates == []
    assert len(report_outbound.enqueued) == 1
    report = report_outbound.enqueued[0]
    assert report["recipient"] == "test.spedition@sandahls.com"
    assert report["sender_mailbox"] == "qinora.ai@sandahls.com"
    assert "8500" in report["body_text"]


def test_finalize_batch_escalates_when_no_carrier_responded() -> None:
    batch = [_rfq("rfq-1", status="expired")]
    collector, fakes = _build_collector(batch=batch, offers=[])

    result = anyio.run(lambda: collector.finalize_batch("req-1"))

    assert result is not None
    assert result.escalated is True
    assert result.quote is None
    assert fakes["task_repository"].created == [
        {"entity_type": "transport_request", "entity_id": "req-1", "reason": NO_RESPONSE_REASON}
    ]


def test_finalize_batch_returns_none_while_rfqs_still_outstanding() -> None:
    batch = [_rfq("rfq-1", status="sent")]
    collector, _fakes = _build_collector(batch=batch, offers=[])

    result = anyio.run(lambda: collector.finalize_batch("req-1"))

    assert result is None


# --- finalize_customer_quote ---------------------------------------------


def test_finalize_customer_quote_prices_and_sends_using_the_winning_offer() -> None:
    winning = _rfq("rfq-1")
    offers = [_offer("off-1", carrier_rfq_id="rfq-1", price=8500.0)]
    history = [_inbound("mail-1")]
    collector, fakes = _build_collector(
        batch=[winning], offers=offers, history=history, winning=winning
    )

    result = anyio.run(lambda: collector.finalize_customer_quote("req-1"))

    assert result is not None
    assert result.escalated is False
    assert result.quote is not None
    assert result.quote.customer_price == 9775.0
    assert fakes["outbound"].enqueued[0].recipient == "customer@example.com"


def test_finalize_customer_quote_returns_none_without_a_winning_rfq() -> None:
    collector, _fakes = _build_collector(batch=[], offers=[], winning=None)

    result = anyio.run(lambda: collector.finalize_customer_quote("req-1"))

    assert result is None


def test_finalize_customer_quote_uses_first_customer_email_despite_thread_contamination() -> None:
    # Reproduced live 2026-09-16: by the time finalize_customer_quote() runs
    # (triggered by the offer-report email arriving back in the customer
    # mailbox), the thread already contains the carrier's own reply AND the
    # offer-report email itself. Picking the LATEST non-excluded message
    # would still be fragile against any future unanticipated row; this
    # locks in that the customer is identified from the message that opened
    # the request, not whatever is newest in the thread.
    winning = _rfq("rfq-1")
    offers = [_offer("off-1", carrier_rfq_id="rfq-1", price=8500.0)]
    history = [
        _inbound("mail-1", sender="real.customer@example.com"),
        _inbound("mail-2", sender="carrier@nordic.example", classification="carrier_offer"),
        _inbound(
            "mail-3",
            sender="qinora.ai@sandahls.com",
            classification="carrier_offer_report",
        ),
    ]
    collector, fakes = _build_collector(
        batch=[winning], offers=offers, history=history, winning=winning
    )

    result = anyio.run(lambda: collector.finalize_customer_quote("req-1"))

    assert result is not None
    assert result.quote is not None
    sent_reply = fakes["outbound"].enqueued[0]
    assert sent_reply.recipient == "real.customer@example.com"
    assert sent_reply.recipient != "qinora.ai@sandahls.com"


def test_quote_customer_escalates_when_no_customer_email_on_thread() -> None:
    winning = _rfq("rfq-1")
    offers = [_offer("off-1", carrier_rfq_id="rfq-1", price=8500.0)]
    # Only non-customer rows in the thread - no one to quote.
    history = [
        _inbound("mail-1", sender="qinora.ai@sandahls.com", classification="carrier_offer_report")
    ]
    collector, fakes = _build_collector(
        batch=[winning], offers=offers, history=history, winning=winning
    )

    result = anyio.run(lambda: collector.finalize_customer_quote("req-1"))

    assert result is not None
    assert result.escalated is True
    assert result.quote is None
    assert fakes["task_repository"].created == [
        {"entity_type": "transport_request", "entity_id": "req-1", "reason": NO_RECIPIENT_REASON}
    ]


def test_finalize_customer_quote_backfills_quote_id_onto_the_original_thread() -> None:
    # link_quote_to_request lets a later customer reply (accept/reject/
    # revise) resolve back to this quote via thread_matching's tier-1
    # message-id match, even though the quote didn't exist yet when the
    # original request email was first linked - see EmailThreadRepository
    # .link_quote_to_request's docstring.
    winning = _rfq("rfq-1")
    offers = [_offer("off-1", carrier_rfq_id="rfq-1", price=8500.0)]
    history = [_inbound("mail-1")]
    collector, fakes = _build_collector(
        batch=[winning], offers=offers, history=history, winning=winning
    )

    result = anyio.run(lambda: collector.finalize_customer_quote("req-1"))

    assert result is not None
    assert fakes["email_threads"].linked_quotes == [("req-1", result.quote.id)]
