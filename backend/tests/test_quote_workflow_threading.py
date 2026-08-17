from dataclasses import dataclass, field, replace

import anyio

from qinora.application.operational_queries import OperationalQueries
from qinora.application.quote_workflow import QuoteWorkflow, SendQuoteCommand
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


def _inbound(message_id: str) -> InboundEmailRecord:
    return InboundEmailRecord(
        id="email-1",
        sender="customer@example.com",
        recipient="farah@qinora.org",
        subject="Fraktforfragan",
        body_text="...",
        classification="transport_request",
        message_id=message_id,
        in_reply_to=None,
        references_header=None,
        request_id="req-1",
        quote_id=None,
        created_at="2026-01-01T00:00:00",
    )


def test_send_quote_threads_onto_latest_inbound_message() -> None:
    history = [_inbound("<first@mail.example.com>"), _inbound("<latest@mail.example.com>")]
    workflow, outbound = _quote_workflow(history)

    async def run():
        return await workflow.send_quote(
            SendQuoteCommand(quote_id="quo-1", recipient="customer@example.com")
        )

    anyio.run(run)

    assert len(outbound.enqueued) == 1
    assert outbound.enqueued[0].in_reply_to_message_id == "<latest@mail.example.com>"


def test_send_quote_has_no_reply_target_when_thread_is_empty() -> None:
    workflow, outbound = _quote_workflow(history=[])

    async def run():
        return await workflow.send_quote(
            SendQuoteCommand(quote_id="quo-1", recipient="customer@example.com")
        )

    anyio.run(run)

    assert outbound.enqueued[0].in_reply_to_message_id is None
