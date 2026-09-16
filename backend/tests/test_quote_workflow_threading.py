from dataclasses import dataclass, field, replace

import anyio

from qinora.application.operational_queries import OperationalQueries
from qinora.application.quote_workflow import (
    QuoteWorkflow,
    SendQuoteCommand,
    first_customer_email,
    latest_customer_email,
)
from qinora.application.read_models import (
    InboundEmailRecord,
    OutboundReplyRecord,
    QuoteRecord,
    RequestRecord,
)
from qinora.domain import CurrencyCode, Money, Quote, QuoteStatus


@dataclass
class FakeQuoteWriteRepository:
    quotes: dict = field(default_factory=dict)

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

    async def mark_quote_sent(self, quote_id):
        self.quotes[quote_id] = replace(self.quotes[quote_id], status="sent")
        return self.quotes[quote_id]


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
        record = OutboundReplyRecord(
            id="reply-1",
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


@dataclass
class FakeOperationalReadRepository:
    request: RequestRecord

    async def list_requests(self):
        return [self.request]


@dataclass
class FakeEmailThreadRepository:
    history: list

    async def list_thread_history(self, *, request_id, quote_id):
        return self.history


def _quote_workflow(
    history: list[InboundEmailRecord],
) -> tuple[QuoteWorkflow, FakeOutboundReplyRepository]:
    quote_repo = FakeQuoteWriteRepository(
        quotes={
            "quo-1": QuoteRecord(
                id="quo-1",
                status="draft",
                version=1,
                customer_price=1000.0,
                currency="SEK",
                parent_quote_id=None,
                request_id="req-1",
            )
        }
    )
    outbound = FakeOutboundReplyRepository()
    operational_queries = OperationalQueries(
        FakeOperationalReadRepository(
            request=RequestRecord(
                id="req-1",
                public_id="REQ-0001",
                customer="Acme AB",
                lane="Gothenburg -> Malmo",
                mode="ltl",
                status="parsed",
                weight_kg=800.0,
            )
        )
    )
    email_threads = FakeEmailThreadRepository(history=history)
    workflow = QuoteWorkflow(quote_repo, outbound, operational_queries, email_threads)
    return workflow, outbound


def _inbound(
    message_id: str,
    sender_name: str | None = None,
    *,
    sender: str = "customer@example.com",
    classification: str = "transport_request",
    email_id: str = "email-1",
) -> InboundEmailRecord:
    return InboundEmailRecord(
        id=email_id,
        sender=sender,
        recipient="farah@qinora.org",
        subject="Fraktforfragan",
        body_text="...",
        classification=classification,
        message_id=message_id,
        in_reply_to=None,
        references_header=None,
        request_id="req-1",
        quote_id=None,
        created_at="2026-01-01T00:00:00",
        sender_name=sender_name,
    )


def test_send_quote_threads_onto_latest_inbound_message() -> None:
    history = [
        _inbound("<first@mail.example.com>", sender_name="Old Name"),
        _inbound("<latest@mail.example.com>", sender_name="Adam Algorf"),
    ]
    workflow, outbound = _quote_workflow(history)

    async def run():
        return await workflow.send_quote(
            SendQuoteCommand(quote_id="quo-1", recipient="customer@example.com")
        )

    anyio.run(run)

    assert len(outbound.enqueued) == 1
    assert outbound.enqueued[0].in_reply_to_message_id == "<latest@mail.example.com>"
    assert outbound.enqueued[0].body_text.startswith("Hej Adam!")


def test_send_quote_has_no_reply_target_when_thread_is_empty() -> None:
    workflow, outbound = _quote_workflow(history=[])

    async def run():
        return await workflow.send_quote(
            SendQuoteCommand(quote_id="quo-1", recipient="customer@example.com")
        )

    anyio.run(run)

    assert outbound.enqueued[0].in_reply_to_message_id is None


def test_latest_customer_email_skips_carrier_offer_report_at_end_of_thread() -> None:
    # Reproduced live 2026-09-16: qinora.ai@ reports the winning carrier
    # rate back to test.spedition@ as the newest row in the thread. Picking
    # it as "the customer to reply to" sent the customer's own quote back to
    # qinora.ai@ instead of the customer - see quote_workflow.py's
    # _NON_CUSTOMER_CLASSIFICATIONS docstring.
    history = [
        _inbound("<opening@mail.example.com>", "Real Customer"),
        _inbound(
            "<report@mail.example.com>",
            "Qinora",
            sender="qinora.ai@sandahls.com",
            classification="carrier_offer_report",
        ),
    ]

    result = latest_customer_email(history)

    assert result is not None
    assert result.message_id == "<opening@mail.example.com>"
    assert result.sender == "customer@example.com"


def test_first_customer_email_stays_fixed_regardless_of_later_thread_contamination() -> None:
    # first_customer_email() must keep pointing at whoever opened the
    # request even when later noise lands in the thread (a carrier reply, an
    # offer report, a stray bounce) - carrier_rfq_collector.py._quote_customer
    # uses this specifically so "who do we quote" never drifts. See
    # first_customer_email()'s own docstring for the full incident history.
    opening = _inbound("<opening@mail.example.com>", "Real Customer")
    carrier_reply = _inbound(
        "<carrier@mail.example.com>",
        "Carrier Co",
        sender="carrier@example.com",
        classification="carrier_offer",
        email_id="email-2",
    )
    offer_report = _inbound(
        "<report@mail.example.com>",
        "Qinora",
        sender="qinora.ai@sandahls.com",
        classification="carrier_offer_report",
        email_id="email-3",
    )
    history = [opening, carrier_reply, offer_report]

    result = first_customer_email(history)

    assert result is not None
    assert result.message_id == "<opening@mail.example.com>"
    assert result.sender == "customer@example.com"


def test_first_customer_email_returns_none_when_thread_has_no_customer_message() -> None:
    history = [
        _inbound(
            "<report@mail.example.com>",
            "Qinora",
            sender="qinora.ai@sandahls.com",
            classification="carrier_offer_report",
        ),
    ]

    assert first_customer_email(history) is None
