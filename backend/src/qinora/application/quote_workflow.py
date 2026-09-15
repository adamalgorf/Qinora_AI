from dataclasses import dataclass

from qinora.application.greeting import greeting
from qinora.application.operational_queries import OperationalQueries
from qinora.application.ports import (
    EmailThreadRepository,
    OutboundReplyRepository,
    QuoteWriteRepository,
)
from qinora.application.read_models import (
    InboundEmailRecord,
    OutboundReplyRecord,
    QuoteRecord,
    RequestRecord,
)
from qinora.domain import can_send_quote

QUOTABLE_REQUEST_STATUSES = {
    "parsed",
    "quoted",
    # A request sitting in an open carrier RFQ batch (see
    # application/pricing_engine.py's carrier-sourcing branch) is still
    # quotable once application/carrier_rfq_collector.py picks a winning
    # offer - it just hasn't been priced yet.
    "sourcing",
}


@dataclass(frozen=True)
class CreateQuoteCommand:
    request_id: str
    customer_price: float
    currency: str = "SEK"


@dataclass(frozen=True)
class SendQuoteCommand:
    quote_id: str
    recipient: str = "customer@example.com"


@dataclass(frozen=True)
class SendQuoteResult:
    quote: QuoteRecord
    outbound_reply: OutboundReplyRecord


class QuoteWorkflow:
    def __init__(
        self,
        repository: QuoteWriteRepository,
        outbound_repository: OutboundReplyRepository,
        operational_queries: OperationalQueries,
        email_threads: EmailThreadRepository | None = None,
        customer_mailbox: str | None = None,
    ) -> None:
        self._repository = repository
        self._outbound_repository = outbound_repository
        self._operational_queries = operational_queries
        self._email_threads = email_threads
        # Which mailbox customer-facing quotes should be sent from (e.g.
        # test.spedition@sandahls.com) when more than one Outlook bridge
        # instance is running - see workers/outlook_bridge.py. None means
        # "any bridge instance may send it" (single-mailbox deployments).
        self._customer_mailbox = customer_mailbox

    async def create_quote(self, command: CreateQuoteCommand) -> QuoteRecord:
        request = await self._find_request(command.request_id)
        if request is None:
            raise RequestNotFoundError(command.request_id)
        if request.status not in QUOTABLE_REQUEST_STATUSES:
            raise RequestNotQuotableError(request.id, request.status)

        return await self._repository.create_quote(
            request_id=command.request_id,
            customer_price=command.customer_price,
            currency=command.currency,
        )

    async def send_quote(self, command: SendQuoteCommand) -> SendQuoteResult:
        quote = await self._repository.get_quote(command.quote_id)

        if quote is None:
            raise QuoteNotFoundError(command.quote_id)

        allowed, reason = can_send_quote(quote)
        if not allowed:
            raise PricingGateError(reason or "Quote cannot be sent")

        sent_quote = await self._repository.mark_quote_sent(command.quote_id)
        request = (
            await self._find_request(sent_quote.request_id) if sent_quote.request_id else None
        )
        latest_message = await self._latest_thread_email(sent_quote)
        greeting_line = greeting(
            latest_message.sender_name if latest_message else None,
            latest_message.sender if latest_message else command.recipient,
        )
        outbound_reply = await self._outbound_repository.enqueue_quote(
            quote_id=sent_quote.id,
            recipient=command.recipient,
            subject=f"Din offert - {sent_quote.id}",
            body_text=_format_quote_body(sent_quote, request, greeting_line),
            in_reply_to_message_id=latest_message.message_id if latest_message else None,
            sender_mailbox=self._customer_mailbox,
        )
        return SendQuoteResult(quote=sent_quote, outbound_reply=outbound_reply)

    async def _latest_thread_email(self, quote: QuoteRecord) -> InboundEmailRecord | None:
        # Sends the quote as an actual reply on the customer's own thread
        # (see integrations/gmail-intake-bridge/Code.gs's sendQueuedReplies())
        # rather than a disconnected new email - replies onto whichever
        # inbound message in the thread is most recent, matching how a
        # human would hit "Reply". Also the source of the sender's name for
        # the greeting (application/greeting.py).
        if self._email_threads is None:
            return None
        history = await self._email_threads.list_thread_history(
            request_id=quote.request_id, quote_id=quote.id
        )
        return latest_customer_email(history)

    async def _find_request(self, request_id: str) -> RequestRecord | None:
        for request in await self._operational_queries.list_requests():
            if request.id == request_id:
                return request
        return None


# "carrier_offer" (application/email_intake_orchestrator.py's
# _handle_carrier_reply) is the one classification that isn't customer mail:
# a transport_request's email thread links both the customer's own messages
# and, once carrier sourcing starts (application/pricing_engine.py), the
# carrier's replies - all keyed to the same request_id, but a carrier reply
# lives in a different physical mailbox (e.g. qinora.ai@ vs test.spedition@ -
# see workers/outlook_bridge.py's per-mailbox bridge instances). Picking a
# carrier reply as "the message to reply to" here would have the wrong
# bridge instance try to find it via Graph, fail (it's not in that mailbox),
# and silently fall back to sending a brand new, unthreaded email instead of
# a reply in the customer's own thread - reproduced live 2026-09-15.
_CARRIER_CLASSIFICATION = "carrier_offer"


def latest_customer_email(
    history: list[InboundEmailRecord],
) -> InboundEmailRecord | None:
    customer_messages = [row for row in history if row.classification != _CARRIER_CLASSIFICATION]
    return customer_messages[-1] if customer_messages else None


def _format_quote_body(
    quote: QuoteRecord, request: RequestRecord | None, greeting_line: str
) -> str:
    # Matches the Rutt/Transportläge/Vikt/Pris + "Ska vi boka?" convention
    # already established in this mailbox's quote history (real quotes sent
    # before this pass, e.g. "Rutt, Ludvika -> Rotterdam. Transportläge,
    # FTL. Pris, 137500.00 SEK. Offerten galler i 7 dagar. Ska vi boka?"),
    # rather than inventing a new, less complete format from scratch.
    # Greets by first name (application/greeting.py) so it reads as a human
    # reply, not a form letter.
    lines = [greeting_line, "", "Tack för din transportförfrågan. Här är vår offert:", ""]
    if request is not None:
        lines.append(f"Rutt: {request.lane}")
        lines.append(f"Transportläge: {request.mode.upper()}")
        if request.weight_kg:
            lines.append(f"Vikt: {request.weight_kg:g} kg")
    lines.append(f"Pris: {quote.customer_price:.2f} {quote.currency}")
    lines.append("")
    lines.append("Offerten gäller i 7 dagar.")
    lines.append("")
    lines.append("Ska vi boka? Svara på detta mail för att godkänna.")
    lines.append("")
    lines.append("Med vänlig hälsning,\nSandahls")
    return "\n".join(lines)


class QuoteNotFoundError(LookupError):
    pass


class RequestNotFoundError(LookupError):
    pass


class RequestNotQuotableError(ValueError):
    def __init__(self, request_id: str, status: str) -> None:
        super().__init__(f"Request {request_id} cannot be quoted while status is {status}")
        self.request_id = request_id
        self.status = status


class PricingGateError(ValueError):
    pass
