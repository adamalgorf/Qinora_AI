from dataclasses import dataclass

from qinora.application.ports import OutboundReplyRepository, QuoteWriteRepository
from qinora.application.read_models import OutboundReplyRecord, QuoteRecord
from qinora.domain import can_send_quote


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
    ) -> None:
        self._repository = repository
        self._outbound_repository = outbound_repository

    async def create_quote(self, command: CreateQuoteCommand) -> QuoteRecord:
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
            subject=f"QiNora quote {sent_quote.id}",
            body_text=(
                "Your transport quote is ready: "
                f"{sent_quote.customer_price:.2f} {sent_quote.currency}."
            ),
        )
        return SendQuoteResult(quote=sent_quote, outbound_reply=outbound_reply)


class QuoteNotFoundError(LookupError):
    pass


class PricingGateError(ValueError):
    pass
