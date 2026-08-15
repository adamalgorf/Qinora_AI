from dataclasses import dataclass

from qinora.application.operational_queries import OperationalQueries
from qinora.application.ports import OutboundReplyRepository, QuoteWriteRepository
from qinora.application.read_models import OutboundReplyRecord, QuoteRecord, RequestRecord
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
    ) -> None:
        self._repository = repository
        self._outbound_repository = outbound_repository
        self._operational_queries = operational_queries

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
        outbound_reply = await self._outbound_repository.enqueue_quote(
            quote_id=sent_quote.id,
            recipient=command.recipient,
            subject=f"Din offert - {sent_quote.id}",
            body_text=(
                f"Din offert är klar: {sent_quote.customer_price:.2f} {sent_quote.currency}.\n\n"
                "Svara på detta mail för att godkänna.\n\n"
                "Med vänlig hälsning,\nSandahls"
            ),
        )
        return SendQuoteResult(quote=sent_quote, outbound_reply=outbound_reply)

    async def _find_request(self, request_id: str) -> RequestRecord | None:
        for request in await self._operational_queries.list_requests():
            if request.id == request_id:
                return request
        return None


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
